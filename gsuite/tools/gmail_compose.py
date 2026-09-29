"""Gmail compose tools — create, update, and delete drafts; send messages.

The `gmail.send` feature was declared but wired to no tool. These handlers
fill it: `gmail_create_draft` (preferred — user reviews/sends from their mail
client), `gmail_update_draft` / `gmail_delete_draft` for revising drafts in
place instead of trash-and-recreate, and `gmail_send_message` (direct send,
for when the user explicitly approves). `gmail_list_drafts` finds drafts the
user started in Gmail, and `gmail_edit_draft` changes only what's asked on
one (attachments, text, recipients) without rebuilding it. All authenticate
as the instance's account and send as that mailbox.
"""

from __future__ import annotations

import base64
import email
import email.policy
import fnmatch
import html
import io
import mimetypes
import os
import re
from email import encoders
from email.message import EmailMessage
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from ..auth import build_service
from ._errors import error
from ._registry import tool
from .gmail_classify import _header, _walk_parts


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


def _drive_fetch(file_id: str) -> tuple[str, str, str, bytes]:
    """Download a binary Drive file → (name, maintype, subtype, bytes)."""
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
    return name, maintype, subtype, buf.getvalue()


def _drive_part(file_id: str) -> MIMEBase:
    """Download a Drive file by id and build an attachment MIME part.

    Binary/uploaded files only — native Google Docs/Sheets/Slides can't be
    fetched via get_media (they'd need an export); attach those as PDFs instead.
    """
    name, maintype, subtype, data = _drive_fetch(file_id)
    part = MIMEBase(maintype, subtype)
    part.set_payload(data)
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


# --- existing drafts: find + surgical edit -----------------------------------
#
# gmail_update_draft rebuilds a draft from scratch, which flattens a draft the
# user started in Gmail (formatted quote, inline images, threading headers).
# These two reach a draft Claude didn't create and change only what's asked.


def _part_header(part: dict[str, Any], name: str) -> str:
    for h in part.get("headers", []) or []:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _api_attachments(message: dict[str, Any]) -> list[dict[str, Any]]:
    """Attachment summary from an API-format (format=full) message payload."""
    out: list[dict[str, Any]] = []
    for part in _walk_parts(message.get("payload", {}) or {}):
        filename = part.get("filename") or ""
        if not filename:
            continue
        disposition = _part_header(part, "Content-Disposition").lower()
        out.append(
            {
                "filename": filename,
                "mimeType": part.get("mimeType", ""),
                "size": (part.get("body") or {}).get("size", 0),
                "inline": disposition.startswith("inline")
                or (not disposition and bool(_part_header(part, "Content-ID"))),
            }
        )
    return out


@tool(
    name="gmail_list_drafts",
    feature="gmail.send",
    description=(
        "List the account's Gmail drafts, including ones the user started "
        "themselves in Gmail. Optional `query` uses Gmail search syntax (e.g. "
        "'to:ollie', 'subject:offer'). Returns each draft's draft_id (the handle "
        "for gmail_edit_draft / gmail_send_draft / gmail_delete_draft), "
        "message_id, thread_id, to, cc, subject, date, snippet, and attachments "
        "(filename, mimeType, size, inline)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Gmail search query to filter drafts; empty = all.",
            },
            "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
        },
    },
)
def list_drafts(query: str = "", limit: int = 20) -> dict[str, Any]:
    svc = _gmail()
    params: dict[str, Any] = {"userId": "me", "maxResults": max(1, min(limit, 100))}
    if query:
        params["q"] = query
    resp = svc.users().drafts().list(**params).execute()
    drafts: list[dict[str, Any]] = []
    for d in resp.get("drafts", []) or []:
        full = svc.users().drafts().get(userId="me", id=d["id"], format="full").execute()
        msg = full.get("message") or {}
        drafts.append(
            {
                "draft_id": full.get("id", d["id"]),
                "message_id": msg.get("id", ""),
                "thread_id": msg.get("threadId", ""),
                "to": _header(msg, "To"),
                "cc": _header(msg, "Cc"),
                "subject": _header(msg, "Subject"),
                "date": _header(msg, "Date"),
                "snippet": msg.get("snippet", ""),
                "attachments": _api_attachments(msg),
            }
        )
    return {"query": query, "count": len(drafts), "drafts": drafts}


def _load_draft_mime(svc: Any, draft_id: str) -> tuple[EmailMessage, dict[str, Any]]:
    d = svc.users().drafts().get(userId="me", id=draft_id, format="raw").execute()
    meta = d.get("message") or {}
    raw = meta.get("raw", "")
    data = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    return email.message_from_bytes(data, policy=email.policy.default), meta


def _mime_attachments(msg: EmailMessage) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for part in msg.walk():
        if part.is_multipart() or not part.get_filename():
            continue
        out.append(
            {
                "filename": part.get_filename(),
                "mimeType": part.get_content_type(),
                "inline": part.get_content_disposition() != "attachment",
            }
        )
    return out


def _body_parts(msg: EmailMessage) -> list[EmailMessage]:
    """The editable text bodies — text/plain + text/html that aren't attachments."""
    return [
        p
        for p in msg.walk()
        if p.get_content_type() in ("text/plain", "text/html")
        and p.get_content_disposition() != "attachment"
        and not p.get_filename()
    ]


def _set_text(part: EmailMessage, text: str) -> None:
    part.set_content(
        text, subtype=part.get_content_subtype(), charset="utf-8", cte="quoted-printable"
    )


def _remove_matching(msg: EmailMessage, patterns: list[str]) -> tuple[list[dict[str, Any]], set[str]]:
    """Drop leaf parts whose filename matches any pattern (exact or glob).

    Returns (removed summaries, patterns that matched nothing). Content-IDs of
    removed inline images come back in the summaries so their <img> tags can
    be stripped from the HTML body too.
    """
    removed: list[dict[str, Any]] = []
    hit: set[str] = set()
    for container in [p for p in msg.walk() if p.is_multipart()]:
        keep = []
        for child in container.get_payload():
            name = None if child.is_multipart() else child.get_filename()
            matched = [pat for pat in patterns if name and fnmatch.fnmatchcase(name, pat)]
            if matched:
                hit.update(matched)
                removed.append(
                    {
                        "filename": name,
                        "mimeType": child.get_content_type(),
                        "content_id": (child.get("Content-ID") or "").strip("<> "),
                    }
                )
            else:
                keep.append(child)
        container.set_payload(keep)
    return removed, set(patterns) - hit


def _strip_cid_images(html_text: str, cids: list[str]) -> str:
    for cid in cids:
        html_text = re.sub(
            r"<img\b[^>]*\bsrc\s*=\s*[\"']?cid:" + re.escape(cid) + r"[\"']?[^>]*>",
            "",
            html_text,
            flags=re.IGNORECASE,
        )
    return html_text


_html_escapes = (
    lambda t: html.escape(t, quote=False),
    lambda t: html.escape(t, quote=True),
    lambda t: html.escape(t, quote=True).replace("&#x27;", "&#39;"),
)


@tool(
    name="gmail_edit_draft",
    feature="gmail.send",
    description=(
        "Surgically edit an EXISTING Gmail draft in place (does NOT send) — "
        "including drafts the user started in Gmail; find them with "
        "gmail_list_drafts. Changes ONLY what is asked and keeps everything "
        "else byte-for-byte: formatted quoted replies, inline images, threading "
        "headers. Operations: remove_attachments (filenames or globs like "
        "'Outlook-*.png'; removing an inline image also drops its <img> from the "
        "HTML body), add_attachments (local paths), add_drive_file_ids, "
        "replace_text ([{find, replace}] across plain + HTML bodies), and "
        "to/cc/bcc/subject overrides ('' clears cc/bcc). Every remove pattern "
        "and find string must match or nothing is written. dry_run=true "
        "reports the changes without saving. Prefer this over gmail_update_draft "
        "for any draft with content worth keeping."
    ),
    input_schema={
        "type": "object",
        "required": ["draft_id"],
        "properties": {
            "draft_id": {
                "type": "string",
                "description": "Draft id from gmail_list_drafts or gmail_create_draft.",
            },
            "remove_attachments": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filenames or glob patterns of attachments/inline images to remove.",
            },
            "add_attachments": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Local filesystem paths to attach.",
            },
            "add_drive_file_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Drive file IDs to download and attach (binary files only).",
            },
            "replace_text": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["find", "replace"],
                    "properties": {
                        "find": {"type": "string"},
                        "replace": {"type": "string"},
                    },
                },
                "description": "Literal find→replace pairs applied to every text body part.",
            },
            "to": {"type": "string"},
            "cc": {"type": "string"},
            "bcc": {"type": "string"},
            "subject": {"type": "string"},
            "dry_run": {"type": "boolean", "default": False},
        },
    },
)
def edit_draft(
    draft_id: str,
    remove_attachments: list[str] | None = None,
    add_attachments: list[str] | None = None,
    add_drive_file_ids: list[str] | None = None,
    replace_text: list[dict[str, str]] | None = None,
    to: str | None = None,
    cc: str | None = None,
    bcc: str | None = None,
    subject: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    if not any(
        [remove_attachments, add_attachments, add_drive_file_ids, replace_text]
    ) and all(v is None for v in (to, cc, bcc, subject)):
        return error("nothing to change — pass at least one edit")
    for path in add_attachments or []:
        if not os.path.isfile(path):
            return error(f"attachment not found: {path}")

    svc = _gmail()
    msg, meta = _load_draft_mime(svc, draft_id)
    before = _mime_attachments(msg)

    removed: list[dict[str, Any]] = []
    if remove_attachments:
        removed, unmatched = _remove_matching(msg, remove_attachments)
        if unmatched:
            return error(
                "no attachment matched: " + ", ".join(sorted(unmatched)),
                available=[a["filename"] for a in before],
            )
        cids = [r["content_id"] for r in removed if r["content_id"]]
        if cids:
            for part in _body_parts(msg):
                if part.get_content_type() == "text/html":
                    text = part.get_content()
                    stripped = _strip_cid_images(text, cids)
                    if stripped != text:
                        _set_text(part, stripped)

    replacements: list[dict[str, Any]] = []
    for pair in replace_text or []:
        find, repl = pair.get("find", ""), pair.get("replace", "")
        if not find:
            return error("replace_text entry has an empty 'find'")
        count = 0
        for part in _body_parts(msg):
            text = part.get_content()
            f, r = find, repl
            if part.get_content_type() == "text/html" and find not in text:
                # The HTML body escapes what the plain body keeps raw — and
                # Gmail spells an apostrophe &#39; where Python says &#x27;.
                for esc in _html_escapes:
                    if esc(find) in text:
                        f, r = esc(find), esc(repl)
                        break
            n = text.count(f)
            if n:
                _set_text(part, text.replace(f, r))
                count += n
        if not count:
            return error(f"text not found in the draft body: {find!r}")
        replacements.append({"find": find, "count": count})

    for header, value in (("To", to), ("Cc", cc), ("Bcc", bcc), ("Subject", subject)):
        if value is None:
            continue
        del msg[header]
        if value:
            msg[header] = value

    added: list[str] = []
    for path in add_attachments or []:
        ctype, _ = mimetypes.guess_type(path)
        maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
        with open(path, "rb") as f:
            msg.add_attachment(
                f.read(), maintype=maintype, subtype=subtype,
                filename=os.path.basename(path),
            )
        added.append(os.path.basename(path))
    for file_id in add_drive_file_ids or []:
        name, maintype, subtype, data = _drive_fetch(file_id)
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
        added.append(name)

    result: dict[str, Any] = {
        "draft_id": draft_id,
        "thread_id": meta.get("threadId", ""),
        "to": msg.get("To", ""),
        "subject": msg.get("Subject", ""),
        "removed": [r["filename"] for r in removed],
        "added": added,
        "replacements": replacements,
        "attachments": _mime_attachments(msg),
        "dry_run": dry_run,
    }
    if dry_run:
        return result

    message: dict[str, Any] = {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode()}
    if meta.get("threadId"):
        message["threadId"] = meta["threadId"]
    draft = (
        svc.users().drafts().update(userId="me", id=draft_id, body={"message": message}).execute()
    )
    result["message_id"] = (draft.get("message") or {}).get("id", "")
    return result
