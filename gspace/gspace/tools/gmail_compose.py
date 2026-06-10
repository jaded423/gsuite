"""Gmail compose tools — create drafts and send messages.

The `gmail.send` feature was declared but wired to no tool. These two handlers
fill it: `gmail_create_draft` (preferred — user reviews/sends from their mail
client) and `gmail_send_message` (direct send, for when the user explicitly
approves). Both authenticate as the instance's account and send as that mailbox.
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
