"""Gmail message read/search tools.

Fills the gap where the `gmail.read` feature (scope gmail.readonly) was enabled
but no tool actually surfaced message content. `gmail_search_messages` finds
messages by Gmail query; `gmail_read_message` returns headers + body, with an
`auth` block (SPF/DKIM/DMARC) handy for verifying outbound deliverability.
"""

from __future__ import annotations

import base64
import os
import re
from typing import Any

from ..auth import build_service
from ._registry import tool
# Reuse the battle-tested body/header extraction from the classify module.
from .gmail_classify import _extract_body, _header, _walk_parts


def _gmail():
    return build_service("gmail")


# Headers worth returning for a quick look without dumping the full set.
_SUMMARY_HEADERS = ("From", "To", "Cc", "Subject", "Date", "Message-Id")


def _list_attachments(msg: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect attachment parts (filename + attachmentId) from a full message."""
    out: list[dict[str, Any]] = []
    for part in _walk_parts(msg.get("payload", {}) or {}):
        filename = part.get("filename") or ""
        body = part.get("body") or {}
        att_id = body.get("attachmentId")
        if filename and att_id:
            out.append(
                {
                    "filename": filename,
                    "mimeType": part.get("mimeType", ""),
                    "size": body.get("size", 0),
                    "attachmentId": att_id,
                }
            )
    return out


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
        "checks), labelIds, and an 'attachments' array (filename + attachmentId "
        "for gmail_get_attachment) when any are present. Set include_body=false "
        "for headers only."
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
    attachments = _list_attachments(msg)
    if attachments:
        out["attachments"] = attachments
    if include_body:
        body = _extract_body(msg)
        if max_body_chars and len(body) > max_body_chars:
            body = body[:max_body_chars] + "\n…[truncated]"
        out["body"] = body
    return out


@tool(
    name="gmail_get_attachment",
    feature="gmail.read",
    description=(
        "Download a Gmail attachment to a local path. Get message_id + "
        "attachment_id from gmail_read_message's 'attachments' array. Optionally "
        "also uploads a copy to a Drive folder (drive_folder_id). Returns "
        "{saved_to, bytes} plus {drive_file_id, drive_link} when uploaded."
    ),
    input_schema={
        "type": "object",
        "required": ["message_id", "attachment_id", "save_path"],
        "properties": {
            "message_id": {"type": "string", "description": "The message id."},
            "attachment_id": {
                "type": "string",
                "description": "attachmentId from gmail_read_message.",
            },
            "save_path": {
                "type": "string",
                "description": "Local filesystem path to write the file to.",
            },
            "drive_folder_id": {
                "type": "string",
                "description": "Optional Drive folder id to also upload a copy into.",
            },
        },
    },
)
def get_attachment(
    message_id: str,
    attachment_id: str,
    save_path: str,
    drive_folder_id: str | None = None,
) -> dict[str, Any]:
    svc = _gmail()
    att = (
        svc.users()
        .messages()
        .attachments()
        .get(userId="me", messageId=message_id, id=attachment_id)
        .execute()
    )
    data_b64 = att.get("data", "")
    data = base64.urlsafe_b64decode(data_b64 + "=" * (-len(data_b64) % 4))
    parent = os.path.dirname(os.path.abspath(save_path))
    os.makedirs(parent, exist_ok=True)
    with open(save_path, "wb") as f:
        f.write(data)
    result: dict[str, Any] = {"saved_to": save_path, "bytes": len(data)}
    if drive_folder_id:
        from googleapiclient.http import MediaFileUpload

        drive = build_service("drive")
        up = (
            drive.files()
            .create(
                body={"name": os.path.basename(save_path), "parents": [drive_folder_id]},
                media_body=MediaFileUpload(save_path),
                fields="id,webViewLink",
            )
            .execute()
        )
        result["drive_file_id"] = up.get("id", "")
        result["drive_link"] = up.get("webViewLink", "")
    return result


def _message_summary(
    msg: dict[str, Any], include_body: bool, max_body_chars: int
) -> dict[str, Any]:
    """Compact single-message view for thread listings."""
    out: dict[str, Any] = {
        "id": msg["id"],
        "from": _header(msg, "From"),
        "to": _header(msg, "To"),
        "date": _header(msg, "Date"),
        "subject": _header(msg, "Subject"),
        "snippet": msg.get("snippet", ""),
        "labelIds": msg.get("labelIds", []),
    }
    attachments = _list_attachments(msg)
    if attachments:
        out["attachments"] = attachments
    if include_body:
        body = _extract_body(msg)
        if max_body_chars and len(body) > max_body_chars:
            body = body[:max_body_chars] + "\n…[truncated]"
        out["body"] = body
    return out


@tool(
    name="gmail_get_thread",
    feature="gmail.read",
    description=(
        "Read a whole Gmail conversation in one call — far cheaper than calling "
        "gmail_read_message per message. Get thread_id from a gmail_search_messages "
        "or gmail_read_message result. Returns {thread_id, count, messages:[...]}, "
        "each message a compact {id, from, to, date, subject, snippet, labelIds, "
        "attachments?}. Set include_body=true to also get each (truncated) body — "
        "off by default to keep long threads lean."
    ),
    input_schema={
        "type": "object",
        "required": ["thread_id"],
        "properties": {
            "thread_id": {"type": "string", "description": "The Gmail threadId."},
            "include_body": {"type": "boolean", "default": False},
            "max_body_chars": {"type": "integer", "default": 8000, "minimum": 0},
            "max_messages": {
                "type": "integer",
                "minimum": 1,
                "description": "Optional cap; keeps the newest N messages in the thread.",
            },
        },
    },
)
def get_thread(
    thread_id: str,
    include_body: bool = False,
    max_body_chars: int = 8000,
    max_messages: int | None = None,
) -> dict[str, Any]:
    svc = _gmail()
    thread = (
        svc.users().threads().get(userId="me", id=thread_id, format="full").execute()
    )
    messages = thread.get("messages", []) or []
    if max_messages and len(messages) > max_messages:
        messages = messages[-max_messages:]
    summaries = [
        _message_summary(m, include_body, max_body_chars) for m in messages
    ]
    return {
        "thread_id": thread.get("id", thread_id),
        "count": len(summaries),
        "messages": summaries,
    }
