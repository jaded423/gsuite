"""Gmail message read/search tools.

Fills the gap where the `gmail.read` feature (scope gmail.readonly) was enabled
but no tool actually surfaced message content. `gmail_search_messages` finds
messages by Gmail query; `gmail_read_message` returns headers + body, with an
`auth` block (SPF/DKIM/DMARC) handy for verifying outbound deliverability.
"""

from __future__ import annotations

import re
from typing import Any

from ..auth import build_service
from ._registry import tool
# Reuse the battle-tested body/header extraction from the classify module.
from .gmail_classify import _extract_body, _header


def _gmail():
    return build_service("gmail")


# Headers worth returning for a quick look without dumping the full set.
_SUMMARY_HEADERS = ("From", "To", "Cc", "Subject", "Date", "Message-Id")


def _parse_auth_results(message: dict[str, Any]) -> dict[str, str]:
    """Pull spf/dkim/dmarc verdicts out of Authentication-Results.

    Returns {} when the header is absent (e.g. a message you sent, viewed from
    Sent). Verdicts are lowercased single words like 'pass' / 'fail' / 'none'.
    """
    raw = _header(message, "Authentication-Results") or _header(
        message, "ARC-Authentication-Results"
    )
    out: dict[str, str] = {}
    for mech in ("spf", "dkim", "dmarc"):
        m = re.search(rf"\b{mech}=(\w+)", raw, re.IGNORECASE)
        if m:
            out[mech] = m.group(1).lower()
    return out


@tool(
    name="gmail_search_messages",
    feature="gmail.read",
    description=(
        "Search Gmail messages with Google's query syntax (e.g. "
        "'from:me subject:invoice newer_than:7d'). Returns a list of "
        "{id, threadId, from, subject, date, snippet}. Use gmail_read_message "
        "with an id for the full headers + body."
    ),
    input_schema={
        "type": "object",
        "required": ["query"],
        "properties": {
            "query": {"type": "string", "description": "Gmail search query."},
            "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
            "label_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional label IDs to scope the search.",
            },
        },
    },
)
def search_messages(
    query: str, limit: int = 20, label_ids: list[str] | None = None
) -> dict[str, Any]:
    svc = _gmail()
    listing = (
        svc.users()
        .messages()
        .list(userId="me", q=query, maxResults=limit, labelIds=label_ids or None)
        .execute()
    )
    ids = [m["id"] for m in listing.get("messages", [])]
    results = []
    for mid in ids:
        msg = (
            svc.users()
            .messages()
            .get(
                userId="me",
                id=mid,
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            )
            .execute()
        )
        results.append(
            {
                "id": msg["id"],
                "threadId": msg.get("threadId", ""),
                "from": _header(msg, "From"),
                "subject": _header(msg, "Subject"),
                "date": _header(msg, "Date"),
                "snippet": msg.get("snippet", ""),
            }
        )
    return {"query": query, "count": len(results), "messages": results}


@tool(
    name="gmail_read_message",
    feature="gmail.read",
    description=(
        "Read one Gmail message by id. Returns summary headers, the text body, "
        "an 'auth' block with spf/dkim/dmarc verdicts (for deliverability "
        "checks), and labelIds. Set include_body=false for headers only."
    ),
    input_schema={
        "type": "object",
        "required": ["id"],
        "properties": {
            "id": {"type": "string"},
            "include_body": {"type": "boolean", "default": True},
            "max_body_chars": {"type": "integer", "default": 8000, "minimum": 0},
            "all_headers": {
                "type": "boolean",
                "default": False,
                "description": "Return every header, not just the summary set.",
            },
        },
    },
)
def read_message(
    id: str,
    include_body: bool = True,
    max_body_chars: int = 8000,
    all_headers: bool = False,
) -> dict[str, Any]:
    svc = _gmail()
    msg = svc.users().messages().get(userId="me", id=id, format="full").execute()

    if all_headers:
        headers = {
            h["name"]: h["value"]
            for h in (msg.get("payload", {}) or {}).get("headers", []) or []
        }
    else:
        headers = {h: _header(msg, h) for h in _SUMMARY_HEADERS}
        headers = {k: v for k, v in headers.items() if v}

    out: dict[str, Any] = {
        "id": msg["id"],
        "threadId": msg.get("threadId", ""),
        "labelIds": msg.get("labelIds", []),
        "snippet": msg.get("snippet", ""),
        "headers": headers,
        "auth": _parse_auth_results(msg),
    }
    if include_body:
        body = _extract_body(msg)
        if max_body_chars and len(body) > max_body_chars:
            body = body[:max_body_chars] + "\n…[truncated]"
        out["body"] = body
    return out
