"""Tests for Google Calendar tools."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gsuite.tools import calendar_tools


@pytest.fixture
def fake_svc(monkeypatch):
    svc = MagicMock()
    monkeypatch.setattr(calendar_tools, "_svc", lambda: svc)
    return svc


def test_list_events_passes_time_window(fake_svc):
    fake_svc.events.return_value.list.return_value.execute.return_value = {
        "items": [{
            "id": "E1", "summary": "Standup",
            "start": {"dateTime": "2026-04-17T09:00:00-05:00"},
            "end": {"dateTime": "2026-04-17T09:30:00-05:00"},
            "attendees": [{"email": "a@b.com", "responseStatus": "accepted"}],
        }]
    }
    out = calendar_tools.calendar_list_events(
        time_min="2026-04-17T00:00:00-05:00",
        time_max="2026-04-18T00:00:00-05:00",
    )
    assert out["count"] == 1
    assert out["events"][0]["summary"] == "Standup"
    assert out["events"][0]["attendees"][0]["email"] == "a@b.com"

    kwargs = fake_svc.events.return_value.list.call_args.kwargs
    assert kwargs["timeMin"] == "2026-04-17T00:00:00-05:00"
    assert kwargs["timeMax"] == "2026-04-18T00:00:00-05:00"
    assert kwargs["singleEvents"] is True
    assert kwargs["orderBy"] == "startTime"


def test_list_events_omits_optional_params(fake_svc):
    fake_svc.events.return_value.list.return_value.execute.return_value = {"items": []}
    calendar_tools.calendar_list_events()
    kwargs = fake_svc.events.return_value.list.call_args.kwargs
    assert "timeMin" not in kwargs
    assert "q" not in kwargs


def test_create_event_builds_body(fake_svc):
    fake_svc.events.return_value.insert.return_value.execute.return_value = {
        "id": "NEW", "summary": "Demo",
        "start": {"dateTime": "2026-05-01T10:00:00-05:00"},
        "end": {"dateTime": "2026-05-01T11:00:00-05:00"},
    }
    out = calendar_tools.calendar_create_event(
        summary="Demo",
        start="2026-05-01T10:00:00-05:00",
        end="2026-05-01T11:00:00-05:00",
        attendees=["guest@x.com"],
        description="desc",
    )
    assert out["id"] == "NEW"
    kwargs = fake_svc.events.return_value.insert.call_args.kwargs
    body = kwargs["body"]
    assert body["summary"] == "Demo"
    assert body["description"] == "desc"
    assert body["attendees"] == [{"email": "guest@x.com"}]
    assert kwargs["sendUpdates"] == "none"


def test_create_event_send_updates_override(fake_svc):
    fake_svc.events.return_value.insert.return_value.execute.return_value = {
        "id": "N", "start": {}, "end": {}
    }
    calendar_tools.calendar_create_event(
        summary="x",
        start="2026-05-01T10:00:00-05:00",
        end="2026-05-01T11:00:00-05:00",
        send_updates="all",
    )
    kwargs = fake_svc.events.return_value.insert.call_args.kwargs
    assert kwargs["sendUpdates"] == "all"


def test_update_event_rejects_empty_patch():
    out = calendar_tools.calendar_update_event(event_id="E")
    assert out["ok"] is False


def test_update_event_patches_only_provided_fields(fake_svc):
    fake_svc.events.return_value.patch.return_value.execute.return_value = {
        "id": "E", "summary": "Renamed", "start": {}, "end": {},
    }
    out = calendar_tools.calendar_update_event(event_id="E", summary="Renamed")
    assert out["summary"] == "Renamed"
    body = fake_svc.events.return_value.patch.call_args.kwargs["body"]
    assert body == {"summary": "Renamed"}
