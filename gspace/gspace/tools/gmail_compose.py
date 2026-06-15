"""Gmail compose tools — create, update, and delete drafts; send messages.

The `gmail.send` feature was declared but wired to no tool. These handlers
fill it: `gmail_create_draft` (preferred — user reviews/sends from their mail
client), `gmail_update_draft` / `gmail_delete_draft` for revising drafts in
place instead of trash-and-recreate, and `gmail_send_message` (direct send,
for when the user explicitly approves). All authenticate as the instance's
account and send as that mailbox.
"""

from __future__ import annotations

import base64
from email.mime.text import MIMEText
from typing import Any

from ..auth import build_service
from ._registry import tool


def _gmail():
    return build_service("gmail")


def _build_raw(
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    bcc: str | None = None,
    reply_to: str | None = None,
) -> dict[str, str]:
    msg = MIMEText(body)
    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc
    if bcc:
        msg["Bcc"] = bcc
    if reply_to:
        msg["Reply-To"] = reply_to
    # From is omitted on purpose — Gmail stamps the authenticated mailbox.
    return {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode()}


_COMPOSE_PROPS = {
    "to": {"type": "string", "description": "Recipient address(es), comma-separated."},
    "subject": {"type": "string"},
    "body": {"type": "string", "description": "Plain-text body."},
    "cc": {"type": "string"},
    "bcc": {"type": "string"},
    "reply_to": {"type": "string"},
}


@tool(
    name="gmail_create_draft",
    feature="gmail.send",
    description=(
        "Create a Gmail draft (does NOT send) in the account's mailbox. Returns "
        "{draft_id, message_id, thread_id}. Preferred over gmail_send_message — "
        "the user reviews and sends from their mail client."
    ),
    input_schema={
        "type": "object",
        "required": ["to", "subject", "body"],
        "properties": _COMPOSE_PROPS,
    },
)
def create_draft(
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    bcc: str | None = None,
    reply_to: str | None = None,
) -> dict[str, Any]:
    svc = _gmail()
    raw = _build_raw(to, subject, body, cc, bcc, reply_to)
    draft = (
        svc.users()
        .drafts()
        .create(userId="me", body={"message": raw})
        .execute()
    )
    return {
        "draft_id": draft.get("id", ""),
        "message_id": (draft.get("message") or {}).get("id", ""),
        "thread_id": (draft.get("message") or {}).get("threadId", ""),
        "to": to,
        "subject": subject,
    }


@tool(
    name="gmail_update_draft",
    feature="gmail.send",
    description=(
        "Replace the content of an existing Gmail draft in place (does NOT "
        "send). Keeps the same draft_id and thread; the message_id changes. "
        "Full replacement — pass the complete to/subject/body, not a diff. "
        "Returns {draft_id, message_id, thread_id}."
    ),
    input_schema={
        "type": "object",
        "required": ["draft_id", "to", "subject", "body"],
        "properties": {
            "draft_id": {
                "type": "string",
                "description": "Draft id from gmail_create_draft or the Drafts list.",
            },
            **_COMPOSE_PROPS,
        },
    },
)
def update_draft(
    draft_id: str,
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    bcc: str | None = None,
    reply_to: str | None = None,
) -> dict[str, Any]:
    svc = _gmail()
    raw = _build_raw(to, subject, body, cc, bcc, reply_to)
    draft = (
        svc.users()
        .drafts()
        .update(userId="me", id=draft_id, body={"message": raw})
        .execute()
    )
    return {
        "draft_id": draft.get("id", ""),
        "message_id": (draft.get("message") or {}).get("id", ""),
        "thread_id": (draft.get("message") or {}).get("threadId", ""),
        "to": to,
        "subject": subject,
    }


@tool(
    name="gmail_delete_draft",
    feature="gmail.send",
    description=(
        "Permanently delete a Gmail draft (does not go to Trash, cannot be "
        "undone). Returns {deleted: true, draft_id}."
    ),
    input_schema={
        "type": "object",
        "required": ["draft_id"],
        "properties": {
            "draft_id": {
                "type": "string",
                "description": "Draft id from gmail_create_draft or the Drafts list.",
            },
        },
    },
)
def delete_draft(draft_id: str) -> dict[str, Any]:
    svc = _gmail()
    svc.users().drafts().delete(userId="me", id=draft_id).execute()
    return {"deleted": True, "draft_id": draft_id}


@tool(
    name="gmail_send_message",
    feature="gmail.send",
    description=(
        "Send an email immediately from the account's mailbox. Returns "
        "{message_id, thread_id}. Only use after the user explicitly approves "
        "sending — otherwise create a draft with gmail_create_draft."
    ),
    input_schema={
        "type": "object",
        "required": ["to", "subject", "body"],
        "properties": _COMPOSE_PROPS,
    },
)
def send_message(
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    bcc: str | None = None,
    reply_to: str | None = None,
) -> dict[str, Any]:
    svc = _gmail()
    raw = _build_raw(to, subject, body, cc, bcc, reply_to)
    sent = svc.users().messages().send(userId="me", body=raw).execute()
    return {
        "message_id": sent.get("id", ""),
        "thread_id": sent.get("threadId", ""),
        "to": to,
        "subject": subject,
    }
