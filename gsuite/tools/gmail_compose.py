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
import io
import mimetypes
import os
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from ..auth import build_service
from ._registry import tool


def _gmail():
    return build_service("gmail")


def _drive():
    return build_service("drive")


def _local_part(path: str) -> MIMEBase:
    """Build an attachment MIME part from a local file path."""
    with open(path, "rb") as f:
        data = f.read()
    ctype, _ = mimetypes.guess_type(path)
    maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
    part = MIMEBase(maintype, subtype)
    part.set_payload(data)
    encoders.encode_base64(part)
    part.add_header(
        "Content-Disposition", "attachment", filename=os.path.basename(path)
    )
    return part


def _drive_part(file_id: str) -> MIMEBase:
    """Download a Drive file by id and build an attachment MIME part.

    Binary/uploaded files only — native Google Docs/Sheets/Slides can't be
    fetched via get_media (they'd need an export); attach those as PDFs instead.
    """
    from googleapiclient.http import MediaIoBaseDownload

    drive = _drive()
    meta = drive.files().get(fileId=file_id, fields="name,mimeType").execute()
    name = meta.get("name", file_id)
    ctype = meta.get("mimeType") or "application/octet-stream"
    maintype, subtype = ctype.split("/", 1) if "/" in ctype else (
        "application",
        "octet-stream",
    )
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, drive.files().get_media(fileId=file_id))
    done = False
    while not done:
        _, done = dl.next_chunk()
    part = MIMEBase(maintype, subtype)
    part.set_payload(buf.getvalue())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", "attachment", filename=name)
    return part


def _build_raw(
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    bcc: str | None = None,
    reply_to: str | None = None,
    body_type: str = "plain",
    attachments: list[str] | None = None,
    drive_file_ids: list[str] | None = None,
    in_reply_to: str | None = None,
    references: str | None = None,
) -> dict[str, str]:
    text_part = MIMEText(body, "html" if body_type == "html" else "plain")
    attach_parts = [_local_part(p) for p in (attachments or [])]
    attach_parts += [_drive_part(f) for f in (drive_file_ids or [])]
    if attach_parts:
        msg: Any = MIMEMultipart()
        msg.attach(text_part)
        for p in attach_parts:
            msg.attach(p)
    else:
        msg = text_part
    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc
    if bcc:
        msg["Bcc"] = bcc
    if reply_to:
        msg["Reply-To"] = reply_to
    if in_reply_to:
        # Thread the reply for real: both headers are needed by mail clients.
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = references or in_reply_to
    # From is omitted on purpose — Gmail stamps the authenticated mailbox.
    return {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode()}


def _message_body(raw: dict[str, str], thread_id: str | None) -> dict[str, Any]:
    """Wrap the raw MIME into a Gmail message body, threading it if asked."""
    message: dict[str, Any] = dict(raw)
    if thread_id:
        message["threadId"] = thread_id
    return message


_COMPOSE_PROPS = {
    "to": {"type": "string", "description": "Recipient address(es), comma-separated."},
    "subject": {"type": "string"},
    "body": {"type": "string", "description": "Body text; plain-text unless body_type=html."},
    "cc": {"type": "string"},
    "bcc": {"type": "string"},
    "reply_to": {"type": "string"},
    "body_type": {
        "type": "string",
        "enum": ["plain", "html"],
        "default": "plain",
        "description": "Set to 'html' to send an HTML body.",
    },
    "attachments": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Local filesystem paths to attach.",
    },
    "drive_file_ids": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Drive file IDs to download and attach (binary files only).",
    },
    "thread_id": {
        "type": "string",
        "description": "Gmail threadId to attach this message to (for replies).",
    },
    "in_reply_to": {
        "type": "string",
        "description": "Message-Id header of the message being replied to (sets In-Reply-To/References so it threads in mail clients).",
    },
    "references": {
        "type": "string",
        "description": "Optional References header; defaults to in_reply_to when omitted.",
    },
}


@tool(
    name="gmail_create_draft",
    feature="gmail.send",
    description=(
        "Create a Gmail draft (does NOT send) in the account's mailbox. Returns "
        "{draft_id, message_id, thread_id}. Preferred over gmail_send_message — "
        "the user reviews and sends from their mail client. Supports HTML "
        "(body_type=html), attachments (local paths and/or Drive file IDs), and "
        "replying in-thread (thread_id + in_reply_to)."
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
    body_type: str = "plain",
    attachments: list[str] | None = None,
    drive_file_ids: list[str] | None = None,
    thread_id: str | None = None,
    in_reply_to: str | None = None,
    references: str | None = None,
) -> dict[str, Any]:
    svc = _gmail()
    raw = _build_raw(
        to, subject, body, cc, bcc, reply_to,
        body_type, attachments, drive_file_ids, in_reply_to, references,
    )
    draft = (
        svc.users()
        .drafts()
        .create(userId="me", body={"message": _message_body(raw, thread_id)})
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
    body_type: str = "plain",
    attachments: list[str] | None = None,
    drive_file_ids: list[str] | None = None,
    thread_id: str | None = None,
    in_reply_to: str | None = None,
    references: str | None = None,
) -> dict[str, Any]:
    svc = _gmail()
    raw = _build_raw(
        to, subject, body, cc, bcc, reply_to,
        body_type, attachments, drive_file_ids, in_reply_to, references,
    )
    draft = (
        svc.users()
        .drafts()
        .update(userId="me", id=draft_id, body={"message": _message_body(raw, thread_id)})
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
        "sending — otherwise create a draft with gmail_create_draft. Supports "
        "HTML (body_type=html), attachments (local paths and/or Drive file IDs), "
        "and replying in-thread (thread_id + in_reply_to)."
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
    body_type: str = "plain",
    attachments: list[str] | None = None,
    drive_file_ids: list[str] | None = None,
    thread_id: str | None = None,
    in_reply_to: str | None = None,
    references: str | None = None,
) -> dict[str, Any]:
    svc = _gmail()
    raw = _build_raw(
        to, subject, body, cc, bcc, reply_to,
        body_type, attachments, drive_file_ids, in_reply_to, references,
    )
    sent = (
        svc.users()
        .messages()
        .send(userId="me", body=_message_body(raw, thread_id))
        .execute()
    )
    return {
        "message_id": sent.get("id", ""),
        "thread_id": sent.get("threadId", ""),
        "to": to,
        "subject": subject,
    }


@tool(
    name="gmail_send_draft",
    feature="gmail.send",
    description=(
        "Send an existing Gmail draft by its draft_id (from gmail_create_draft "
        "or the Drafts list). Returns {message_id, thread_id, draft_id}. Only "
        "use after the user approves sending."
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
def send_draft(draft_id: str) -> dict[str, Any]:
    svc = _gmail()
    sent = svc.users().drafts().send(userId="me", body={"id": draft_id}).execute()
    return {
        "message_id": sent.get("id", ""),
        "thread_id": sent.get("threadId", ""),
        "draft_id": draft_id,
    }
