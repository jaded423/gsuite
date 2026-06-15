"""Tests for Google Docs tools."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gsuite.tools import docs_tools


@pytest.fixture
def fake_svc(monkeypatch):
    svc = MagicMock()
    monkeypatch.setattr(docs_tools, "_svc", lambda: svc)
    return svc


def _get_returns(svc, payload):
    svc.documents.return_value.get.return_value.execute.return_value = payload


def _create_returns(svc, payload):
    svc.documents.return_value.create.return_value.execute.return_value = payload


def _batch_update_returns(svc, payload):
    svc.documents.return_value.batchUpdate.return_value.execute.return_value = payload


def test_read_extracts_flat_text(fake_svc):
    _get_returns(fake_svc, {
        "title": "Doc A",
        "body": {"content": [
            {"paragraph": {"elements": [
                {"textRun": {"content": "Hello "}},
                {"textRun": {"content": "world\n"}},
            ]}},
            {"paragraph": {"elements": [{"textRun": {"content": "Second line.\n"}}]}},
        ]},
    })
    out = docs_tools.docs_read("DOC_ID")
    assert out["title"] == "Doc A"
    assert out["text"] == "Hello world\nSecond line.\n"


def test_create_without_text_skips_batch_update(fake_svc):
    _create_returns(fake_svc, {"documentId": "DOC1"})
    out = docs_tools.docs_create("Title")
    assert out["document_id"] == "DOC1"
    fake_svc.documents.return_value.batchUpdate.assert_not_called()


def test_create_with_text_inserts_body(fake_svc):
    _create_returns(fake_svc, {"documentId": "DOC1"})
    _batch_update_returns(fake_svc, {"replies": []})
    docs_tools.docs_create("Title", text="Body content")
    body = fake_svc.documents.return_value.batchUpdate.call_args.kwargs["body"]
    assert body["requests"][0]["insertText"]["text"] == "Body content"
    assert body["requests"][0]["insertText"]["location"]["index"] == 1


def test_append_text_rejects_empty():
    out = docs_tools.docs_append_text("DOC", "")
    assert out["ok"] is False


def test_append_text_prefixes_newline(fake_svc):
    _batch_update_returns(fake_svc, {"replies": []})
    docs_tools.docs_append_text("DOC", "more")
    body = fake_svc.documents.return_value.batchUpdate.call_args.kwargs["body"]
    assert body["requests"][0]["insertText"]["text"] == "\nmore"
    assert body["requests"][0]["insertText"]["endOfSegmentLocation"] == {}


def test_find_replace_builds_one_request_per_pair(fake_svc):
    _batch_update_returns(fake_svc, {
        "replies": [
            {"replaceAllText": {"occurrencesChanged": 3}},
            {"replaceAllText": {"occurrencesChanged": 1}},
        ]
    })
    out = docs_tools.docs_find_replace("DOC", {"{{a}}": "A", "{{b}}": "B"})
    assert out["replacements"] == 2
    assert out["occurrences_changed"] == 4
    requests = fake_svc.documents.return_value.batchUpdate.call_args.kwargs["body"]["requests"]
    assert len(requests) == 2
    assert all(r["replaceAllText"]["containsText"]["matchCase"] is True for r in requests)


def test_find_replace_rejects_empty_dict():
    out = docs_tools.docs_find_replace("DOC", {})
    assert out["ok"] is False
