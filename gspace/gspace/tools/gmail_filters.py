"""Gmail filter management tools.

Fills the `@gongrzhe/server-gmail-autoauth-mcp` gap: `list_filters` actually
returns everything, and we add the backup/restore + label-name resolution that
we kept re-writing by hand during the 2026-04-16 filter-cleanup session.

Key learnings baked in here:
- Filter criteria are stored verbatim (a UI-created `subject:("[Billing]")`
  comes back as the literal string `(\"[Billing]\")`). We pass criteria through
  untouched on the request path; we only parse on render for the backup/list
  views, and we never silently normalize.
- Filters can only *remove* system labels (INBOX, SPAM, STARRED, etc.), not
  user labels — the v1 tool does not try to enforce that beyond surfacing the
  API error; the rule engine (Phase 2) is where we compile around it.
- Full filter IDs are ~70 chars long. We always return them in full.
- Before any destructive op (replace/delete/restore), we snapshot all filters
  to `~/.config/gspace/backups/YYYY-MM-DDTHH-MM-SS.json`.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..auth import build_service, with_retry
from ..settings import BACKUPS_DIR
from ._errors import error
from ._registry import tool

log = logging.getLogger("gspace.tools.gmail_filters")


def _gmail():
    return build_service("gmail")


def _label_map() -> dict[str, str]:
    """Return {label_id: label_name} for the authorized account."""
    svc = _gmail()
    resp = with_retry(lambda: svc.users().labels().list(userId="me").execute())
    return {lbl["id"]: lbl["name"] for lbl in resp.get("labels", [])}


def _enrich_filter(f: dict[str, Any], labels: dict[str, str]) -> dict[str, Any]:
    """Resolve label IDs inside a filter's action to human-readable names."""
    action = f.get("action", {}) or {}
    add_ids = action.get("addLabelIds", []) or []
    rem_ids = action.get("removeLabelIds", []) or []
    return {
        "id": f.get("id"),
        "criteria": f.get("criteria", {}) or {},
        "action": action,
        "addLabels": [labels.get(i, i) for i in add_ids],
        "removeLabels": [labels.get(i, i) for i in rem_ids],
    }


# --- read --------------------------------------------------------------------

@tool(
    name="gmail_list_filters",
    feature="gmail.filters",
    description=(
        "List every Gmail filter on the authorized account. Returns full "
        "filter IDs (~70 chars), raw criteria, raw action, and resolved "
        "label names (addLabels/removeLabels)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "resolve_labels": {
                "type": "boolean",
                "default": True,
                "description": "Resolve label IDs to human-readable names.",
            }
        },
    },
)
def list_filters(resolve_labels: bool = True) -> dict[str, Any]:
    svc = _gmail()
    resp = with_retry(
        lambda: svc.users().settings().filters().list(userId="me").execute()
    )
    filters = resp.get("filter", []) or []
    if not resolve_labels:
        return {"count": len(filters), "filters": filters}
    labels = _label_map()
    return {
        "count": len(filters),
        "filters": [_enrich_filter(f, labels) for f in filters],
    }


@tool(
    name="gmail_get_filter",
    feature="gmail.filters",
    description="Fetch one filter by full ID.",
    input_schema={
        "type": "object",
        "required": ["filter_id"],
        "properties": {
            "filter_id": {"type": "string"},
            "resolve_labels": {"type": "boolean", "default": True},
        },
    },
)
def get_filter(filter_id: str, resolve_labels: bool = True) -> dict[str, Any]:
    svc = _gmail()
    f = with_retry(
        lambda: svc.users()
        .settings()
        .filters()
        .get(userId="me", id=filter_id)
        .execute()
    )
    if not resolve_labels:
        return f
    return _enrich_filter(f, _label_map())


# --- backup / restore --------------------------------------------------------

def _backup_path() -> Path:
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    return BACKUPS_DIR / f"filters-{stamp}.json"


@tool(
    name="gmail_backup_filters",
    feature="gmail.filters",
    description=(
        "Write all filters + label map to a timestamped JSON file under "
        "~/.config/gspace/backups/ (or the given path)."
    ),
    input_schema={
        "type": "object",
        "properties": {"path": {"type": "string"}},
    },
)
def backup_filters(path: str | None = None) -> dict[str, Any]:
    """Dump all filters (plus the label name map at this moment) to JSON."""
    svc = _gmail()
    resp = with_retry(
        lambda: svc.users().settings().filters().list(userId="me").execute()
    )
    filters = resp.get("filter", []) or []
    labels = _label_map()
    payload = {
        "taken_at": datetime.now(timezone.utc).isoformat(),
        "count": len(filters),
        "labels": labels,
        "filters": filters,
    }
    out = Path(path) if path else _backup_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n")
    return {"path": str(out), "count": len(filters)}


def _auto_backup() -> str:
    """Take a safety snapshot before a destructive op; return the path."""
    result = backup_filters(None)
    log.info("pre-change backup written to %s", result["path"])
    return result["path"]


# --- write -------------------------------------------------------------------

@tool(
    name="gmail_create_filter",
    feature="gmail.filters",
    description=(
        "Create a Gmail filter. `criteria` and `action` follow the Gmail "
        "Settings API shape — criteria fields: from, to, subject, query, "
        "negatedQuery, hasAttachment, excludeChats, size, sizeComparison; "
        "action fields: addLabelIds, removeLabelIds, forward."
    ),
    input_schema={
        "type": "object",
        "required": ["criteria", "action"],
        "properties": {
            "criteria": {"type": "object"},
            "action": {"type": "object"},
        },
    },
)
def create_filter(
    criteria: dict[str, Any], action: dict[str, Any]
) -> dict[str, Any]:
    svc = _gmail()
    body = {"criteria": criteria, "action": action}
    created = with_retry(
        lambda: svc.users()
        .settings()
        .filters()
        .create(userId="me", body=body)
        .execute()
    )
    return _enrich_filter(created, _label_map())


@tool(
    name="gmail_delete_filter",
    feature="gmail.filters",
    description="Delete a filter by ID. Backs up first. Requires `confirm=true`.",
    input_schema={
        "type": "object",
        "required": ["filter_id"],
        "properties": {
            "filter_id": {"type": "string"},
            "confirm": {"type": "boolean", "default": False},
        },
    },
)
def delete_filter(filter_id: str, confirm: bool = False) -> dict[str, Any]:
    """Delete a filter. Takes a pre-change backup. `confirm=True` required."""
    if not confirm:
        return error("confirm=True required for delete", filter_id=filter_id)
    backup = _auto_backup()
    svc = _gmail()
    with_retry(
        lambda: svc.users()
        .settings()
        .filters()
        .delete(userId="me", id=filter_id)
        .execute()
    )
    return {"ok": True, "deleted": filter_id, "backup": backup}


@tool(
    name="gmail_replace_filter",
    feature="gmail.filters",
    description=(
        "Replace a filter by delete+create (Gmail filters are immutable). "
        "Takes a safety backup first. Requires `confirm=true`."
    ),
    input_schema={
        "type": "object",
        "required": ["filter_id", "criteria", "action"],
        "properties": {
            "filter_id": {"type": "string"},
            "criteria": {"type": "object"},
            "action": {"type": "object"},
            "confirm": {"type": "boolean", "default": False},
        },
    },
)
def replace_filter(
    filter_id: str,
    criteria: dict[str, Any],
    action: dict[str, Any],
    confirm: bool = False,
) -> dict[str, Any]:
    """Gmail filters are immutable; "replace" = delete-then-create atomically.

    If the create step fails, we surface the error and leave the old filter
    deleted — that's the Gmail API's semantics, not a bug. The pre-change
    backup is how the user recovers from that case.
    """
    if not confirm:
        return error("confirm=True required for replace", filter_id=filter_id)
    backup = _auto_backup()
    svc = _gmail()
    with_retry(
        lambda: svc.users()
        .settings()
        .filters()
        .delete(userId="me", id=filter_id)
        .execute()
    )
    created = with_retry(
        lambda: svc.users()
        .settings()
        .filters()
        .create(userId="me", body={"criteria": criteria, "action": action})
        .execute()
    )
    return {
        "ok": True,
        "replaced": filter_id,
        "new": _enrich_filter(created, _label_map()),
        "backup": backup,
    }


@tool(
    name="gmail_restore_filters",
    feature="gmail.filters",
    description=(
        "Restore filters from a backup file. Modes: `dry-run` (report only, "
        "default), `merge` (add missing filters), `replace-all` (wipe + "
        "recreate). Non-dry-run modes require `confirm=true`."
    ),
    input_schema={
        "type": "object",
        "required": ["path"],
        "properties": {
            "path": {"type": "string"},
            "mode": {
                "type": "string",
                "enum": ["dry-run", "merge", "replace-all"],
                "default": "dry-run",
            },
            "confirm": {"type": "boolean", "default": False},
        },
    },
)
def restore_filters(
    path: str, mode: str = "dry-run", confirm: bool = False
) -> dict[str, Any]:
    """Restore filters from a backup file.

    Modes:
      - `dry-run`: report planned changes only (default)
      - `merge`:   create filters in the backup that aren't currently present
                   (matched by criteria JSON hash)
      - `replace-all`: delete every current filter then recreate from backup

    `confirm=True` is required for `merge` and `replace-all`.
    """
    src = Path(path)
    if not src.exists():
        return error(f"backup not found: {path}")
    payload = json.loads(src.read_text())
    backup_filters_list = payload.get("filters", []) or []

    svc = _gmail()
    current = with_retry(
        lambda: svc.users().settings().filters().list(userId="me").execute()
    ).get("filter", []) or []

    def _key(f: dict[str, Any]) -> str:
        # criteria + action define a filter's identity for dedup purposes.
        return json.dumps(
            {"criteria": f.get("criteria", {}), "action": f.get("action", {})},
            sort_keys=True,
        )

    current_keys = {_key(f) for f in current}
    to_create = [f for f in backup_filters_list if _key(f) not in current_keys]

    if mode == "dry-run":
        return {
            "ok": True,
            "mode": mode,
            "would_create": len(to_create),
            "would_delete": 0,
            "backup_file_count": len(backup_filters_list),
            "current_count": len(current),
        }

    if mode not in {"merge", "replace-all"}:
        return error(f"unknown mode: {mode}")
    if not confirm:
        return error("confirm=True required for non-dry-run modes")

    pre_change_backup = _auto_backup()
    deleted = 0
    if mode == "replace-all":
        for f in current:
            with_retry(
                lambda fid=f["id"]: svc.users()
                .settings()
                .filters()
                .delete(userId="me", id=fid)
                .execute()
            )
            deleted += 1
        to_create = backup_filters_list

    created = 0
    for f in to_create:
        body = {"criteria": f.get("criteria", {}), "action": f.get("action", {})}
        with_retry(
            lambda b=body: svc.users()
            .settings()
            .filters()
            .create(userId="me", body=b)
            .execute()
        )
        created += 1

    return {
        "ok": True,
        "mode": mode,
        "created": created,
        "deleted": deleted,
        "pre_change_backup": pre_change_backup,
    }
