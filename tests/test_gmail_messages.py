"""Tests for Gmail read/message tools (search, read, thread, attachment).

Mirrors the sibling read-tool tests. Note: the gmail modules use a `_gmail()`
service seam (not the `_svc()` seam the calendar/drive modules use), so the
fixture patches `_gmail`.
"""

from __future__ import annotations

import base64
from unittest.mock import MagicMock

import pytest

from gsuite.tools import gmail_messages


@pytest.fixture
def fake_svc(monkeypatch):
    svc = MagicMock()
    monkeypatch.setattr(gmail_messages, "_gmail", lambda: svc)
    return svc


def _msg(mid, sender, subject, *, parts=None, snippet="", labels=None):
    """Build a minimal Gmail `messages.get(format=full)` payload."""
    headers = [
        {"name": "From", "value": sender},
        {"name": "To", "value": "me@example.com"},
        {"name": "Subject", "value": subject},
        {"name": "Date", "value": "Mon, 07 Jul 2026 09:00:00 -0500"},
    ]
    payload = {"headers": headers}
    if parts is not None:
        payload["parts"] = parts
    return {
        "id": mid,
        "threadId": "T1",
        "snippet": snippet,
        "labelIds": labels or ["INBOX"],
        "payload": payload,
    }


def _text_part(text):
    data = base64.urlsafe_b64encode(text.encode()).decode()
    return {"mimeType": "text/plain", "body": {"data": data}}


def _attachment_part(filename, att_id, mime="application/pdf", size=1234):
    return {
        "mimeType": mime,
        "filename": filename,
        "body": {"attachmentId": att_id, "size": size},
    }


def test_read_message_surfaces_attachments(fake_svc):
    fake_svc.users.return_value.messages.return_value.get.return_value.execute.return_value = _msg(
        "M1",
        "Alice <alice@example.com>",
        "Invoice",
        parts=[_text_part("hi there"), _attachment_part("invoice.pdf", "ATT9")],
    )
    out = gmail_messages.read_message(id="M1")
    assert out["id"] == "M1"
    assert out["headers"]["From"] == "Alice <alice@example.com>"
    assert out["body"] == "hi there"
    assert out["attachments"] == [
        {"filename": "invoice.pdf", "mimeType": "application/pdf", "size": 1234, "attachmentId": "ATT9"}
    ]
    kwargs = fake_svc.users.return_value.messages.return_value.get.call_args.kwargs
    assert kwargs["id"] == "M1"
    assert kwargs["format"] == "full"


def test_read_message_no_attachments_key_when_none(fake_svc):
    fake_svc.users.return_value.messages.return_value.get.return_value.execute.return_value = _msg(
        "M2", "Bob <bob@example.com>", "Plain", parts=[_text_part("body only")]
    )
    out = gmail_messages.read_message(id="M2")
    assert "attachments" not in out


def test_get_thread_summarizes_each_message(fake_svc):
    fake_svc.users.return_value.threads.return_value.get.return_value.execute.return_value = {
        "id": "T1",
        "messages": [
            _msg("M1", "Alice <alice@example.com>", "Q", snippet="question?"),
            _msg("M2", "Bob <bob@example.com>", "Re: Q", snippet="answer."),
        ],
    }
    out = gmail_messages.get_thread(thread_id="T1")
    assert out["thread_id"] == "T1"
    assert out["count"] == 2
    assert out["messages"][0]["from"] == "Alice <alice@example.com>"
    assert out["messages"][1]["snippet"] == "answer."
    # summaries-only by default → no body
    assert "body" not in out["messages"][0]

    kwargs = fake_svc.users.return_value.threads.return_value.get.call_args.kwargs
    assert kwargs["id"] == "T1"
    assert kwargs["format"] == "full"


def test_get_thread_include_body_and_cap(fake_svc):
    fake_svc.users.return_value.threads.return_value.get.return_value.execute.return_value = {
        "id": "T1",
        "messages": [
            _msg("M1", "Alice <a@x.com>", "Q", parts=[_text_part("first msg")]),
            _msg("M2", "Bob <b@x.com>", "Re", parts=[_text_part("second msg")]),
            _msg("M3", "Cy <c@x.com>", "Re", parts=[_text_part("third msg")]),
        ],
    }
    out = gmail_messages.get_thread(thread_id="T1", include_body=True, max_messages=2)
    # cap keeps the newest 2
    assert out["count"] == 2
    assert [m["id"] for m in out["messages"]] == ["M2", "M3"]
    assert out["messages"][0]["body"] == "second msg"


def test_get_attachment_writes_local_file(fake_svc, tmp_path):
    fake_svc.users.return_value.messages.return_value.attachments.return_value.get.return_value.execute.return_value = {
        "data": base64.urlsafe_b64encode(b"hello attachment").decode()
    }
    dest = tmp_path / "out" / "file.pdf"
    out = gmail_messages.get_attachment(
        message_id="M1", attachment_id="ATT9", save_path=str(dest)
    )
    assert dest.read_bytes() == b"hello attachment"
    assert out["bytes"] == len(b"hello attachment")
    assert out["saved_to"] == str(dest)

    kwargs = fake_svc.users.return_value.messages.return_value.attachments.return_value.get.call_args.kwargs
    assert kwargs["messageId"] == "M1"
    assert kwargs["id"] == "ATT9"
