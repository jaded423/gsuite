"""Tests for gmail_list_drafts / gmail_edit_draft and drive_upload_file.

The edit fixture mirrors a real Gmail reply draft: multipart/mixed wrapping a
multipart/related (plain + HTML alternative, HTML quoting an inline signature
logo by cid) plus a PDF attachment. A MagicMock service stands in for Gmail;
tests decode the raw MIME handed to drafts.update and assert on it.
"""

from __future__ import annotations

import base64
import email
import email.policy
from email.message import EmailMessage
from unittest.mock import MagicMock

import pytest

from gsuite.tools import drive_tools, gmail_compose

QUOTE_HTML = (
    "<div>Good morning Ollie! I&#39;ve attached my signed copy.</div>"
    '<blockquote>Thanks, Ollie<br><img src="cid:logo1@x" width="100"></blockquote>'
)


def _draft_mime() -> EmailMessage:
    msg = EmailMessage()
    msg["To"] = "Ollie <ollie@example.com>"
    msg["Subject"] = "Re: Offer"
    msg["In-Reply-To"] = "<orig@example.com>"
    msg["References"] = "<orig@example.com>"
    msg.set_content("Good morning Ollie! I've attached my signed copy.\n> Thanks, Ollie")
    msg.add_alternative(QUOTE_HTML, subtype="html")
    msg.get_payload()[1].add_related(
        b"\x89PNG-logo", maintype="image", subtype="png",
        cid="<logo1@x>", filename="Outlook-abc.png",
    )
    msg.add_attachment(
        b"%PDF-1.7 signed", maintype="application", subtype="pdf",
        filename="Offer Signed.pdf",
    )
    return msg


@pytest.fixture
def fake_svc(monkeypatch):
    svc = MagicMock()
    monkeypatch.setattr(gmail_compose, "_gmail", lambda: svc)
    raw = base64.urlsafe_b64encode(_draft_mime().as_bytes()).decode()
    drafts = svc.users.return_value.drafts.return_value
    drafts.get.return_value.execute.return_value = {
        "id": "r1", "message": {"id": "m1", "threadId": "T1", "raw": raw},
    }
    drafts.update.return_value.execute.return_value = {
        "id": "r1", "message": {"id": "m2", "threadId": "T1"},
    }
    return svc


def _written(svc) -> tuple[EmailMessage, dict]:
    kwargs = svc.users.return_value.drafts.return_value.update.call_args.kwargs
    message = kwargs["body"]["message"]
    data = base64.urlsafe_b64decode(message["raw"])
    return email.message_from_bytes(data, policy=email.policy.default), message


def _filenames(msg: EmailMessage) -> list[str]:
    return [p.get_filename() for p in msg.walk() if not p.is_multipart() and p.get_filename()]


def _html(msg: EmailMessage) -> str:
    return next(p for p in msg.walk() if p.get_content_type() == "text/html").get_content()


# --- gmail_edit_draft --------------------------------------------------------

def test_remove_inline_image_by_glob_keeps_everything_else(fake_svc):
    out = gmail_compose.edit_draft("r1", remove_attachments=["Outlook-*.png"])
    assert out["removed"] == ["Outlook-abc.png"]
    msg, message = _written(fake_svc)
    assert _filenames(msg) == ["Offer Signed.pdf"]
    html = _html(msg)
    assert "cid:logo1@x" not in html  # dangling <img> stripped with its part
    assert "<blockquote>Thanks, Ollie<br>" in html  # formatted quote untouched
    assert msg["In-Reply-To"] == "<orig@example.com>"
    assert message["threadId"] == "T1"
    assert out["message_id"] == "m2"


def test_unmatched_remove_pattern_writes_nothing(fake_svc):
    out = gmail_compose.edit_draft("r1", remove_attachments=["nope.png"])
    assert out["ok"] is False
    assert "Offer Signed.pdf" in out["available"]
    fake_svc.users.return_value.drafts.return_value.update.assert_not_called()


def test_replace_text_hits_plain_and_escaped_html(fake_svc):
    out = gmail_compose.edit_draft(
        "r1", replace_text=[{"find": "I've attached", "replace": "I've enclosed"}]
    )
    assert out["replacements"] == [{"find": "I've attached", "count": 2}]
    msg, _ = _written(fake_svc)
    plain = next(p for p in msg.walk() if p.get_content_type() == "text/plain").get_content()
    assert "I've enclosed" in plain
    assert "I&#39;ve enclosed" in _html(msg) or "I&#x27;ve enclosed" in _html(msg)


def test_replace_text_missing_writes_nothing(fake_svc):
    out = gmail_compose.edit_draft("r1", replace_text=[{"find": "absent", "replace": "x"}])
    assert out["ok"] is False
    fake_svc.users.return_value.drafts.return_value.update.assert_not_called()


def test_add_attachment_and_headers(fake_svc, tmp_path):
    f = tmp_path / "extra.txt"
    f.write_text("hello")
    out = gmail_compose.edit_draft(
        "r1", add_attachments=[str(f)], cc="cody@example.com", subject="Re: Offer (signed)"
    )
    assert out["added"] == ["extra.txt"]
    msg, _ = _written(fake_svc)
    assert _filenames(msg) == ["Outlook-abc.png", "Offer Signed.pdf", "extra.txt"]
    assert msg["Cc"] == "cody@example.com"
    assert msg["Subject"] == "Re: Offer (signed)"


def test_dry_run_reports_without_writing(fake_svc):
    out = gmail_compose.edit_draft("r1", remove_attachments=["Outlook-abc.png"], dry_run=True)
    assert out["removed"] == ["Outlook-abc.png"]
    assert [a["filename"] for a in out["attachments"]] == ["Offer Signed.pdf"]
    fake_svc.users.return_value.drafts.return_value.update.assert_not_called()


def test_no_edits_is_an_error(fake_svc):
    assert gmail_compose.edit_draft("r1")["ok"] is False


def test_missing_local_attachment_is_an_error(fake_svc):
    out = gmail_compose.edit_draft("r1", add_attachments=["/nonexistent/file.pdf"])
    assert out["ok"] is False


# --- gmail_list_drafts -------------------------------------------------------

def test_list_drafts_returns_handles_and_attachments(fake_svc):
    drafts = fake_svc.users.return_value.drafts.return_value
    drafts.list.return_value.execute.return_value = {"drafts": [{"id": "r1"}]}
    drafts.get.return_value.execute.return_value = {
        "id": "r1",
        "message": {
            "id": "m1", "threadId": "T1", "snippet": "Good morning",
            "payload": {
                "headers": [{"name": "To", "value": "ollie@example.com"},
                            {"name": "Subject", "value": "Re: Offer"}],
                "parts": [
                    {"mimeType": "image/png", "filename": "Outlook-abc.png",
                     "headers": [{"name": "Content-ID", "value": "<logo1@x>"}],
                     "body": {"size": 10}},
                    {"mimeType": "application/pdf", "filename": "Offer Signed.pdf",
                     "headers": [{"name": "Content-Disposition", "value": "attachment"}],
                     "body": {"size": 20}},
                ],
            },
        },
    }
    out = gmail_compose.list_drafts(query="to:ollie", limit=5)
    assert drafts.list.call_args.kwargs == {"userId": "me", "maxResults": 5, "q": "to:ollie"}
    d = out["drafts"][0]
    assert (d["draft_id"], d["thread_id"], d["subject"]) == ("r1", "T1", "Re: Offer")
    assert [(a["filename"], a["inline"]) for a in d["attachments"]] == [
        ("Outlook-abc.png", True), ("Offer Signed.pdf", False),
    ]


# --- drive_upload_file -------------------------------------------------------

def test_upload_file_sends_binary_with_guessed_type(monkeypatch, tmp_path):
    svc = MagicMock()
    monkeypatch.setattr(drive_tools, "_svc", lambda: svc)
    svc.files.return_value.create.return_value.execute.return_value = {"id": "F1", "name": "a.pdf"}
    f = tmp_path / "a.pdf"
    f.write_bytes(b"%PDF-1.7")
    out = drive_tools.drive_upload_file(str(f), parent_id="P1")
    assert out == {"ok": True, "id": "F1", "name": "a.pdf"}
    kwargs = svc.files.return_value.create.call_args.kwargs
    assert kwargs["body"] == {"name": "a.pdf", "parents": ["P1"]}
    assert kwargs["media_body"].mimetype() == "application/pdf"


def test_upload_missing_file_is_an_error(monkeypatch):
    monkeypatch.setattr(drive_tools, "_svc", MagicMock)
    assert drive_tools.drive_upload_file("/nonexistent.pdf")["ok"] is False
