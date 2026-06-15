"""Bulk Gmail operations — the "apply to existing mail" gap.

Gmail filters only apply to *new* mail. Every time we tightened the Billing
filters, ~200 existing messages stayed in the wrong label. These tools close
that gap and become the primitive the rule engine composes on.

Design notes:
- `messages.batchModify` takes up to 1000 IDs per call. We chunk transparently.
- `removeLabelIds` on batchModify accepts user labels (unlike filter actions,
  which reject them). That's why "move mail out of label X" works via batch
  but not via filter coordination alone.
- After a batchModify, search results are eventually consistent — the caller
  should not immediately re-search and expect to see the change. We return the
  count of IDs we touched and leave re-verification to the caller.
- Label-name→ID cache is per-call; labels change rarely but we don't want to
  hand back stale IDs across server lifetimes.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

from ..auth import build_service, with_retry
from ._errors import error
from ._registry import tool

log = logging.getLogger("gsuite.tools.gmail_bulk")

BATCH_MODIFY_CHUNK = 1000
SYSTEM_LABELS = {
    "INBOX", "SPAM", "TRASH", "UNREAD", "STARRED", "IMPORTANT", "SENT",
    "DRAFT", "CHAT", "CATEGORY_PERSONAL", "CATEGORY_SOCIAL", "CATEGORY_PROMOTIONS",
    "CATEGORY_UPDATES", "CATEGORY_FORUMS",
}


def _gmail():
    return build_service("gmail")


# --- label name <-> ID helpers ------------------------------------------------

def _label_index() -> tuple[dict[str, str], dict[str, str]]:
    """Return (name→id, id→name) for every label."""
    svc = _gmail()
    resp = with_retry(lambda: svc.users().labels().list(userId="me").execute())
    labels = resp.get("labels", []) or []
    by_name = {lbl["name"]: lbl["id"] for lbl in labels}
    by_id = {lbl["id"]: lbl["name"] for lbl in labels}
    return by_name, by_id


def _resolve_label(name_or_id: str, by_name: dict[str, str]) -> str:
    """Accept either a label ID (system or user-prefixed 'Label_…') or a name."""
    if name_or_id in SYSTEM_LABELS:
        return name_or_id
    if name_or_id.startswith("Label_"):
        return name_or_id
    if name_or_id in by_name:
        return by_name[name_or_id]
    raise ValueError(
        f"unknown label: {name_or_id!r}. Known: {sorted(by_name)[:10]}…"
    )


def _resolve_labels(names: Iterable[str], by_name: dict[str, str]) -> list[str]:
    return [_resolve_label(n, by_name) for n in names]


# --- criteria → Gmail search query -------------------------------------------

def criteria_to_query(criteria: dict[str, Any]) -> str:
    """Build the Gmail search string that matches a filter's criteria.

    Filter criteria are stored verbatim by Gmail (see learning #2). So a UI-
    created `subject:("[Billing]")` comes back as the literal string
    `(\"[Billing]\")` — we don't strip or re-quote; we just prefix `subject:`.
    """
    parts: list[str] = []
    if v := criteria.get("from"):
        parts.append(f"from:({v})")
    if v := criteria.get("to"):
        parts.append(f"to:({v})")
    if v := criteria.get("subject"):
        parts.append(f"subject:{v}")
    if v := criteria.get("query"):
        parts.append(f"({v})")
    if v := criteria.get("negatedQuery"):
        parts.append(f"-({v})")
    if criteria.get("hasAttachment"):
        parts.append("has:attachment")
    if criteria.get("excludeChats"):
        parts.append("-in:chats")
    if (size := criteria.get("size")) and (cmp := criteria.get("sizeComparison")):
        if cmp == "larger":
            parts.append(f"larger:{size}")
        elif cmp == "smaller":
            parts.append(f"smaller:{size}")
    return " ".join(parts)


# --- core bulk ops -----------------------------------------------------------

def _search_ids(query: str, limit: int | None = None) -> list[str]:
    svc = _gmail()
    ids: list[str] = []
    page_token = None
    while True:
        kwargs = {"userId": "me", "q": query, "maxResults": 500}
        if page_token:
            kwargs["pageToken"] = page_token
        resp = with_retry(lambda: svc.users().messages().list(**kwargs).execute())
        for m in resp.get("messages", []) or []:
            ids.append(m["id"])
            if limit is not None and len(ids) >= limit:
                return ids
        page_token = resp.get("nextPageToken")
        if not page_token:
            return ids


def _chunks(xs: list[str], n: int) -> Iterable[list[str]]:
    for i in range(0, len(xs), n):
        yield xs[i : i + n]


@tool(
    name="gmail_batch_modify",
    feature="gmail.bulk_modify",
    description=(
        "Apply add/remove label changes to every message matching a Gmail "
        "search query. Chunked into 1000-ID batchModify calls. Dry-run by "
        "default — pass dry_run=false to mutate."
    ),
    input_schema={
        "type": "object",
        "required": ["query"],
        "properties": {
            "query": {"type": "string"},
            "add_labels": {"type": "array", "items": {"type": "string"}},
            "remove_labels": {"type": "array", "items": {"type": "string"}},
            "dry_run": {"type": "boolean", "default": True},
            "limit": {"type": "integer", "minimum": 1},
        },
    },
)
def batch_modify(
    query: str,
    add_labels: list[str] | None = None,
    remove_labels: list[str] | None = None,
    dry_run: bool = True,
    limit: int | None = None,
) -> dict[str, Any]:
    """Apply label changes to every message matching `query`.

    Chunks into 1000-ID batchModify calls. `dry_run=True` (default) returns a
    count without mutating anything.
    """
    add_labels = add_labels or []
    remove_labels = remove_labels or []
    if not add_labels and not remove_labels:
        return error("provide add_labels and/or remove_labels")
    by_name, _ = _label_index()
    add_ids = _resolve_labels(add_labels, by_name)
    remove_ids = _resolve_labels(remove_labels, by_name)

    ids = _search_ids(query, limit=limit)
    if dry_run or not ids:
        return {
            "ok": True,
            "dry_run": dry_run,
            "query": query,
            "matched": len(ids),
            "sample_ids": ids[:5],
            "add_label_ids": add_ids,
            "remove_label_ids": remove_ids,
        }

    svc = _gmail()
    touched = 0
    for chunk in _chunks(ids, BATCH_MODIFY_CHUNK):
        body = {"ids": chunk, "addLabelIds": add_ids, "removeLabelIds": remove_ids}
        with_retry(
            lambda b=body: svc.users().messages().batchModify(userId="me", body=b).execute()
        )
        touched += len(chunk)
        log.info("batchModify: touched %d / %d", touched, len(ids))
    return {
        "ok": True,
        "dry_run": False,
        "query": query,
        "modified": touched,
        "add_label_ids": add_ids,
        "remove_label_ids": remove_ids,
    }


@tool(
    name="gmail_reclassify_filter",
    feature="gmail.bulk_modify",
    description=(
        "Apply a filter's action to existing mail that matches its criteria "
        "(Gmail filters only apply to new mail by default). Dry-run default."
    ),
    input_schema={
        "type": "object",
        "required": ["filter_id"],
        "properties": {
            "filter_id": {"type": "string"},
            "dry_run": {"type": "boolean", "default": True},
            "limit": {"type": "integer", "minimum": 1},
        },
    },
)
def reclassify_filter(
    filter_id: str, dry_run: bool = True, limit: int | None = None
) -> dict[str, Any]:
    """Apply a filter's action to existing mail matching its criteria.

    The thing we wrote by hand at the end of the 2026-04-16 session.
    """
    svc = _gmail()
    f = with_retry(
        lambda: svc.users().settings().filters().get(userId="me", id=filter_id).execute()
    )
    query = criteria_to_query(f.get("criteria", {}))
    if not query.strip():
        return error("filter has empty criteria; refusing to match-all")
    action = f.get("action", {}) or {}
    add_ids = action.get("addLabelIds", []) or []
    remove_ids = action.get("removeLabelIds", []) or []
    if not add_ids and not remove_ids:
        return error("filter has no label actions")

    ids = _search_ids(query, limit=limit)
    if dry_run or not ids:
        return {
            "ok": True,
            "dry_run": dry_run,
            "filter_id": filter_id,
            "query": query,
            "matched": len(ids),
            "sample_ids": ids[:5],
            "add_label_ids": add_ids,
            "remove_label_ids": remove_ids,
        }

    touched = 0
    for chunk in _chunks(ids, BATCH_MODIFY_CHUNK):
        body = {"ids": chunk, "addLabelIds": add_ids, "removeLabelIds": remove_ids}
        with_retry(
            lambda b=body: svc.users().messages().batchModify(userId="me", body=b).execute()
        )
        touched += len(chunk)
    return {
        "ok": True,
        "dry_run": False,
        "filter_id": filter_id,
        "query": query,
        "modified": touched,
    }


@tool(
    name="gmail_move_label",
    feature="gmail.bulk_modify",
    description=(
        "Move mail from one label to another (add to_label, remove from_label). "
        "Optional `query` narrows the scope further. Dry-run default."
    ),
    input_schema={
        "type": "object",
        "required": ["from_label", "to_label"],
        "properties": {
            "from_label": {"type": "string"},
            "to_label": {"type": "string"},
            "query": {"type": "string"},
            "dry_run": {"type": "boolean", "default": True},
            "limit": {"type": "integer", "minimum": 1},
        },
    },
)
def move_label(
    from_label: str,
    to_label: str,
    query: str | None = None,
    dry_run: bool = True,
    limit: int | None = None,
) -> dict[str, Any]:
    """Move all mail from one label to another (optionally scoped by query).

    Uses batchModify, so user labels are fine to remove (unlike filter actions).
    """
    q_parts = [f"label:{from_label}"]
    if query:
        q_parts.append(f"({query})")
    q = " ".join(q_parts)
    return batch_modify(
        q, add_labels=[to_label], remove_labels=[from_label], dry_run=dry_run, limit=limit
    )
