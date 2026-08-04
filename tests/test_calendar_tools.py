"""Tests for Google Calendar tools."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gsuite.tools import calendar_tools


@pytest.fixture
def fake_svc(monkeypatch):
    svc = MagicMock()
    monkeypatch.setattr(calendar_tools, "_svc", lambda: svc)
    calendar_tools._TZ_CACHE.clear()
    svc.calendars.return_value.get.return_value.execute.return_value = {
        "id": "primary", "timeZone": "America/Chicago",
    }
    return svc


def _insert_body(svc):
    return svc.events.return_value.insert.call_args.kwargs["body"]


def _patch_body(svc):
    return svc.events.return_value.patch.call_args.kwargs["body"]


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
    # an offset-carrying timestamp is passed through untouched
    assert body["start"] == {"dateTime": "2026-05-01T10:00:00-05:00"}
    assert body["end"] == {"dateTime": "2026-05-01T11:00:00-05:00"}
    # attendees present and send_updates unset -> they get invited
    assert kwargs["sendUpdates"] == "all"


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


# --- time parsing: all-day ---------------------------------------------------

@pytest.fixture
def created(fake_svc):
    """Minimal insert response so create() can flatten a summary."""
    fake_svc.events.return_value.insert.return_value.execute.return_value = {
        "id": "N", "start": {}, "end": {},
    }
    return fake_svc


def test_date_only_start_makes_an_all_day_event(created):
    calendar_tools.calendar_create_event(summary="Deadline", start="2026-07-28")
    body = _insert_body(created)
    assert body["start"] == {"date": "2026-07-28"}
    # Google's all-day end is exclusive: one day means the next date
    assert body["end"] == {"date": "2026-07-29"}
    created.calendars.return_value.get.assert_not_called()


def test_all_day_end_on_the_start_date_is_bumped(created):
    calendar_tools.calendar_create_event(
        summary="Deadline", start="2026-07-28", end="2026-07-28"
    )
    body = _insert_body(created)
    assert body["end"] == {"date": "2026-07-29"}


def test_multi_day_all_day_end_is_left_alone(created):
    calendar_tools.calendar_create_event(
        summary="Trip", start="2026-07-28", end="2026-07-31"
    )
    body = _insert_body(created)
    assert body["start"] == {"date": "2026-07-28"}
    assert body["end"] == {"date": "2026-07-31"}


# --- time parsing: timed -----------------------------------------------------

def test_floating_datetime_gets_the_calendar_timezone(created):
    calendar_tools.calendar_create_event(summary="Standup", start="2026-07-28T09:00")
    body = _insert_body(created)
    assert body["start"] == {
        "dateTime": "2026-07-28T09:00:00", "timeZone": "America/Chicago",
    }
    assert body["end"] == {
        "dateTime": "2026-07-28T09:30:00", "timeZone": "America/Chicago",
    }


def test_explicit_timezone_skips_the_calendar_lookup(created):
    calendar_tools.calendar_create_event(
        summary="Standup", start="2026-07-28T09:00", timezone="America/New_York"
    )
    body = _insert_body(created)
    assert body["start"]["timeZone"] == "America/New_York"
    created.calendars.return_value.get.assert_not_called()


def test_calendar_timezone_is_cached_across_calls(created):
    for _ in range(3):
        calendar_tools.calendar_create_event(summary="x", start="2026-07-28T09:00")
    assert created.calendars.return_value.get.call_count == 1


def test_offset_datetime_needs_no_timezone(created):
    calendar_tools.calendar_create_event(
        summary="Standup", start="2026-07-28T09:00:00-05:00"
    )
    body = _insert_body(created)
    assert "timeZone" not in body["start"]
    assert body["end"]["dateTime"] == "2026-07-28T09:30:00-05:00"
    created.calendars.return_value.get.assert_not_called()


def test_z_suffix_is_accepted(created):
    calendar_tools.calendar_create_event(summary="UTC", start="2026-07-28T14:00:00Z")
    body = _insert_body(created)
    assert body["start"]["dateTime"] == "2026-07-28T14:00:00+00:00"
    assert "timeZone" not in body["start"]


def test_duration_minutes_sets_the_end(created):
    calendar_tools.calendar_create_event(
        summary="Long", start="2026-07-28T09:00", duration_minutes=90
    )
    assert _insert_body(created)["end"]["dateTime"] == "2026-07-28T10:30:00"


# --- time parsing: rejections ------------------------------------------------

def test_mixed_date_and_datetime_is_rejected(fake_svc):
    out = calendar_tools.calendar_create_event(
        summary="x", start="2026-07-28", end="2026-07-28T10:00"
    )
    assert out["ok"] is False
    assert "same shape" in out["error"]
    fake_svc.events.return_value.insert.assert_not_called()


def test_end_before_start_is_rejected(fake_svc):
    out = calendar_tools.calendar_create_event(
        summary="x", start="2026-07-28T10:00", end="2026-07-28T09:00"
    )
    assert out["ok"] is False
    fake_svc.events.return_value.insert.assert_not_called()


def test_unparseable_start_is_rejected(fake_svc):
    out = calendar_tools.calendar_create_event(summary="x", start="next tuesday")
    assert out["ok"] is False
    assert "ISO 8601" in out["error"]
    fake_svc.events.return_value.insert.assert_not_called()


# --- notification defaults ---------------------------------------------------

def test_attendees_are_notified_by_default(created):
    out = calendar_tools.calendar_create_event(
        summary="x", start="2026-07-28T09:00", attendees=["g@x.com"]
    )
    assert created.events.return_value.insert.call_args.kwargs["sendUpdates"] == "all"
    assert out["notified"] == "all"


def test_explicit_none_still_adds_attendees_silently(created):
    calendar_tools.calendar_create_event(
        summary="x", start="2026-07-28T09:00", attendees=["g@x.com"], send_updates="none"
    )
    assert created.events.return_value.insert.call_args.kwargs["sendUpdates"] == "none"


def test_no_attendees_notifies_nobody(created):
    calendar_tools.calendar_create_event(summary="x", start="2026-07-28T09:00")
    assert created.events.return_value.insert.call_args.kwargs["sendUpdates"] == "none"


# --- summary flattening ------------------------------------------------------

def test_summary_flags_all_day_and_timezone():
    out = calendar_tools._event_to_summary(
        {"id": "E", "start": {"date": "2026-07-28"}, "end": {"date": "2026-07-29"}}
    )
    assert out["all_day"] is True
    assert out["start"] == "2026-07-28"

    timed = calendar_tools._event_to_summary({
        "id": "E",
        "start": {"dateTime": "2026-07-28T09:00:00", "timeZone": "America/Chicago"},
        "end": {"dateTime": "2026-07-28T09:30:00"},
    })
    assert timed["all_day"] is False
    assert timed["time_zone"] == "America/Chicago"


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
    # a metadata-only patch never reads the event back
    fake_svc.events.return_value.get.assert_not_called()


@pytest.fixture
def patched(fake_svc):
    """An existing 09:00–09:30 timed event, and a patch response to flatten."""
    fake_svc.events.return_value.get.return_value.execute.return_value = {
        "id": "E",
        "start": {"dateTime": "2026-07-28T09:00:00-05:00"},
        "end": {"dateTime": "2026-07-28T09:30:00-05:00"},
    }
    fake_svc.events.return_value.patch.return_value.execute.return_value = {
        "id": "E", "start": {}, "end": {},
    }
    return fake_svc


def test_moving_start_alone_keeps_the_existing_length(patched):
    calendar_tools.calendar_update_event(event_id="E", start="2026-07-28T14:00:00-05:00")
    body = _patch_body(patched)
    assert body["start"]["dateTime"] == "2026-07-28T14:00:00-05:00"
    assert body["end"]["dateTime"] == "2026-07-28T14:30:00-05:00"


def test_duration_minutes_overrides_the_existing_length(patched):
    calendar_tools.calendar_update_event(
        event_id="E", start="2026-07-28T14:00:00-05:00", duration_minutes=120
    )
    assert _patch_body(patched)["end"]["dateTime"] == "2026-07-28T16:00:00-05:00"


def test_patching_end_alone_reads_the_current_start(patched):
    calendar_tools.calendar_update_event(event_id="E", end="2026-07-28T11:00:00-05:00")
    body = _patch_body(patched)
    assert body["start"]["dateTime"] == "2026-07-28T09:00:00-05:00"
    assert body["end"]["dateTime"] == "2026-07-28T11:00:00-05:00"


def test_flipping_timed_to_all_day_clears_datetime(patched):
    calendar_tools.calendar_update_event(event_id="E", start="2026-07-28")
    body = _patch_body(patched)
    # patch merges nested objects, so the stale key must be explicitly nulled
    assert body["start"] == {"date": "2026-07-28", "dateTime": None}
    assert body["end"] == {"date": "2026-07-29", "dateTime": None}


def test_flipping_all_day_to_timed_clears_date(fake_svc):
    fake_svc.events.return_value.get.return_value.execute.return_value = {
        "id": "E", "start": {"date": "2026-07-28"}, "end": {"date": "2026-07-29"},
    }
    fake_svc.events.return_value.patch.return_value.execute.return_value = {
        "id": "E", "start": {}, "end": {},
    }
    calendar_tools.calendar_update_event(event_id="E", start="2026-07-28T09:00")
    body = _patch_body(fake_svc)
    assert body["start"] == {
        "dateTime": "2026-07-28T09:00:00", "timeZone": "America/Chicago", "date": None,
    }


def test_update_rejects_a_bad_time_without_patching(patched):
    out = calendar_tools.calendar_update_event(event_id="E", start="whenever")
    assert out["ok"] is False
    patched.events.return_value.patch.assert_not_called()


def test_replacing_attendees_notifies_by_default(patched):
    calendar_tools.calendar_update_event(event_id="E", attendees=["g@x.com"])
    assert patched.events.return_value.patch.call_args.kwargs["sendUpdates"] == "all"


# --- new verbs: get / list_calendars / delete / respond ----------------------

def test_get_event(fake_svc):
    fake_svc.events.return_value.get.return_value.execute.return_value = {
        "id": "E", "summary": "One", "start": {}, "end": {},
    }
    out = calendar_tools.calendar_get_event(event_id="E")
    assert out["id"] == "E"
    assert fake_svc.events.return_value.get.call_args.kwargs["eventId"] == "E"


def test_list_calendars(fake_svc):
    fake_svc.calendarList.return_value.list.return_value.execute.return_value = {
        "items": [
            {"id": "primary", "summary": "Me", "primary": True, "accessRole": "owner"},
            {"id": "team@x", "summary": "Team", "accessRole": "writer"},
        ]
    }
    out = calendar_tools.calendar_list_calendars()
    assert out["count"] == 2
    assert out["calendars"][0]["primary"] is True
    assert out["calendars"][1]["primary"] is False


def test_delete_event(fake_svc):
    fake_svc.events.return_value.delete.return_value.execute.return_value = ""
    out = calendar_tools.calendar_delete_event(event_id="E", send_updates="all")
    assert out["deleted"] is True
    kwargs = fake_svc.events.return_value.delete.call_args.kwargs
    assert kwargs["eventId"] == "E"
    assert kwargs["sendUpdates"] == "all"


def test_respond_to_event_sets_self_response(fake_svc):
    fake_svc.events.return_value.get.return_value.execute.return_value = {
        "id": "E", "summary": "Invite", "start": {}, "end": {},
        "attendees": [
            {"email": "other@x.com", "responseStatus": "accepted"},
            {"email": "me@x.com", "self": True, "responseStatus": "needsAction"},
        ],
    }
    fake_svc.events.return_value.patch.return_value.execute.return_value = {
        "id": "E", "summary": "Invite", "start": {}, "end": {},
    }
    out = calendar_tools.calendar_respond_to_event(event_id="E", response="accepted")
    assert out["ok"] is True
    body = fake_svc.events.return_value.patch.call_args.kwargs["body"]
    me = [a for a in body["attendees"] if a.get("self")][0]
    assert me["responseStatus"] == "accepted"
    # other attendee untouched
    other = [a for a in body["attendees"] if not a.get("self")][0]
    assert other["responseStatus"] == "accepted"


def test_respond_to_event_not_attendee(fake_svc):
    fake_svc.events.return_value.get.return_value.execute.return_value = {
        "id": "E", "start": {}, "end": {}, "attendees": [{"email": "x@y.com"}],
    }
    out = calendar_tools.calendar_respond_to_event(event_id="E", response="declined")
    assert out["ok"] is False
