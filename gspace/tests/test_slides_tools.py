"""Tests for Google Slides tools."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gspace.tools import slides_tools


@pytest.fixture
def fake_svc(monkeypatch):
    svc = MagicMock()
    monkeypatch.setattr(slides_tools, "_svc", lambda: svc)
    return svc


def test_read_flattens_textruns_per_slide(fake_svc):
    fake_svc.presentations.return_value.get.return_value.execute.return_value = {
        "title": "Deck A",
        "slides": [
            {
                "objectId": "s1",
                "pageElements": [
                    {"shape": {"text": {"textElements": [
                        {"textRun": {"content": "Title\n"}},
                        {"textRun": {"content": "Body line"}},
                    ]}}}
                ],
            },
            {
                "objectId": "s2",
                "pageElements": [
                    {"shape": {"text": {"textElements": [
                        {"textRun": {"content": "Slide two"}}
                    ]}}}
                ],
            },
        ],
    }
    out = slides_tools.slides_read("PID")
    assert out["slide_count"] == 2
    assert out["slides"][0]["slide_id"] == "s1"
    assert out["slides"][0]["text"].startswith("Title")
    assert "Body line" in out["slides"][0]["text"]


def test_create_returns_url(fake_svc):
    fake_svc.presentations.return_value.create.return_value.execute.return_value = {
        "presentationId": "PID_NEW"
    }
    out = slides_tools.slides_create("My Deck")
    assert out["presentation_id"] == "PID_NEW"
    assert "PID_NEW" in out["url"]


def test_add_slide_rejects_bad_layout():
    out = slides_tools.slides_add_slide("PID", layout="FANCY")
    assert out["ok"] is False


def test_add_slide_sends_predefined_layout(fake_svc):
    fake_svc.presentations.return_value.batchUpdate.return_value.execute.return_value = {
        "replies": [{"createSlide": {"objectId": "new_slide"}}]
    }
    out = slides_tools.slides_add_slide("PID", layout="TITLE_AND_BODY")
    assert out["slide_id"] == "new_slide"
    req = fake_svc.presentations.return_value.batchUpdate.call_args.kwargs["body"]["requests"][0]
    assert req["createSlide"]["slideLayoutReference"]["predefinedLayout"] == "TITLE_AND_BODY"
    assert "insertionIndex" not in req["createSlide"]


def test_add_slide_honors_insertion_index(fake_svc):
    fake_svc.presentations.return_value.batchUpdate.return_value.execute.return_value = {
        "replies": [{"createSlide": {"objectId": "s"}}]
    }
    slides_tools.slides_add_slide("PID", insertion_index=2)
    req = fake_svc.presentations.return_value.batchUpdate.call_args.kwargs["body"]["requests"][0]
    assert req["createSlide"]["insertionIndex"] == 2


def test_replace_text_rejects_empty():
    out = slides_tools.slides_replace_text("PID", {})
    assert out["ok"] is False


def test_replace_text_builds_one_request_per_pair(fake_svc):
    fake_svc.presentations.return_value.batchUpdate.return_value.execute.return_value = {
        "replies": [
            {"replaceAllText": {"occurrencesChanged": 2}},
            {"replaceAllText": {"occurrencesChanged": 0}},
        ]
    }
    out = slides_tools.slides_replace_text("PID", {"{{sop}}": "Onboarding", "{{owner}}": "J"})
    assert out["replacements"] == 2
    assert out["occurrences_changed"] == 2
    reqs = fake_svc.presentations.return_value.batchUpdate.call_args.kwargs["body"]["requests"]
    assert all(r["replaceAllText"]["containsText"]["matchCase"] is True for r in reqs)
