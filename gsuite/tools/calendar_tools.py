"""Google Calendar tools — list events, create event, update event.

Event times accept three shapes, and the tool picks the right Calendar
representation for each:

* `2026-04-17`                    → **all-day** event (`{"date": …}`)
* `2026-04-17T09:00`              → **timed**, floating — stamped with the
  explicit `timezone` argument, else the calendar's own timezone
* `2026-04-17T09:00:00-05:00`     → **timed**, already absolute (`Z` also fine)

`end` is optional: an all-day event runs one day, a timed event runs
`duration_minutes` (default 30). The tools don't parse natural language —
the MCP client resolves "next Tuesday" before calling in.

Default calendar is `primary`, which resolves to the authenticated user's
main calendar.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from typing import Any

from ..auth import build_service, with_retry
from ._errors import error
from ._registry import tool

log = logging.getLogger("gsuite.tools.calendar")

DEFAULT_DURATION_MINUTES = 30

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_OFFSET_RE = re.compile(r"(Z|[+-]\d{2}:?\d{2})$")

# calendar_id -> IANA timezone. Cached per process; a calendar's timezone is a
# setting people change roughly never, and this is on the hot path for every
# floating datetime.
_TZ_CACHE: dict[str, str] = {}


class _TimeError(ValueError):
    """A start/end pair Calendar would reject — reported as a tool error."""


def _svc():
    return build_service("calendar")


def _calendar_timezone(calendar_id: str) -> str:
    """The calendar's own IANA timezone, e.g. `America/Chicago`."""
    if calendar_id not in _TZ_CACHE:
        svc = _svc()
        cal = with_retry(lambda: svc.calendars().get(calendarId=calendar_id).execute())
        _TZ_CACHE[calendar_id] = cal.get("timeZone") or "UTC"
    return _TZ_CACHE[calendar_id]


def _parse_dt(value: str, label: str) -> datetime:
    normalized = value.strip().replace(" ", "T")
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        raise _TimeError(
            f"{label} {value!r} is not ISO 8601 — use YYYY-MM-DD for an all-day "
            "event, or YYYY-MM-DDTHH:MM[:SS][±HH:MM] for a timed one"
        ) from None


def _is_date_only(value: str) -> bool:
    return bool(_DATE_RE.match(value.strip()))


def _event_times(
    start: str,
    end: str | None,
    calendar_id: str,
    timezone: str | None = None,
    duration_minutes: int | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """Build Calendar `start`/`end` objects from loose ISO input.

    All-day when `start` is date-only; timed otherwise. Raises `_TimeError`
    for pairs the API would 400 on (mixed shapes, end before start).
    """
    all_day = _is_date_only(start)
    if end is not None and _is_date_only(end) != all_day:
        raise _TimeError(
            f"start {start!r} and end {end!r} mix an all-day date with a timed "
            "datetime — both must be the same shape"
        )

    if all_day:
        start_d = date.fromisoformat(start.strip())
        end_d = date.fromisoformat(end.strip()) if end else start_d + timedelta(days=1)
        # Google's all-day end is *exclusive*. An end on or before the start is
        # never what the caller meant (and 400s), so read it as "this one day".
        if end_d <= start_d:
            end_d = start_d + timedelta(days=1)
        return {"date": start_d.isoformat()}, {"date": end_d.isoformat()}

    start_dt = _parse_dt(start, "start")
    if end is None:
        end_dt = start_dt + timedelta(
            minutes=duration_minutes or DEFAULT_DURATION_MINUTES
        )
    else:
        end_dt = _parse_dt(end, "end")
        if end_dt <= start_dt:
            raise _TimeError(f"end {end!r} is not after start {start!r}")

    start_obj = {"dateTime": start_dt.isoformat()}
    end_obj = {"dateTime": end_dt.isoformat()}
    # A floating datetime is meaningless to Calendar without a zone; stamp it
    # with the caller's choice, else the calendar's own — never a guess.
    if timezone is None and start_dt.tzinfo is None:
        timezone = _calendar_timezone(calendar_id)
    if timezone:
        start_obj["timeZone"] = timezone
        end_obj["timeZone"] = timezone
    return start_obj, end_obj


def _resolve_send_updates(send_updates: str | None, attendees: list[str] | None) -> str:
    """Adding a guest *is* the intent to invite them.

    Left unset, attendees get notified; pass `send_updates` explicitly to
    override in either direction.
    """
    if send_updates is not None:
        return send_updates
    return "all" if attendees else "none"


def _event_to_summary(ev: dict[str, Any]) -> dict[str, Any]:
    """Flatten a Calendar event to the fields we care about."""
    start = ev.get("start") or {}
    end = ev.get("end") or {}
    return {
        "id": ev.get("id"),
        "summary": ev.get("summary"),
        "description": ev.get("description"),
        "location": ev.get("location"),
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
        "all_day": bool(start.get("date")),
        "time_zone": start.get("timeZone"),
        "attendees": [
            {"email": a.get("email"), "response": a.get("responseStatus")}
            for a in ev.get("attendees", []) or []
        ],
        "html_link": ev.get("htmlLink"),
        "status": ev.get("status"),
    }


@tool(
    name="calendar_list_events",
    feature="calendar.read",
    description=(
        "List events on a calendar within a time window. `time_min` and "
        "`time_max` are ISO 8601 timestamps with timezone. Default calendar "
        "is `primary`. Events are sorted by start time ascending."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "calendar_id": {"type": "string", "default": "primary"},
            "time_min": {"type": "string", "description": "ISO 8601 with TZ"},
            "time_max": {"type": "string", "description": "ISO 8601 with TZ"},
            "max_results": {"type": "integer", "default": 50, "minimum": 1, "maximum": 250},
            "query": {"type": "string", "description": "Free-text filter"},
        },
    },
)
def calendar_list_events(
    calendar_id: str = "primary",
    time_min: str | None = None,
    time_max: str | None = None,
    max_results: int = 50,
    query: str | None = None,
) -> dict[str, Any]:
    svc = _svc()
    params: dict[str, Any] = {
        "calendarId": calendar_id,
        "maxResults": max_results,
        "singleEvents": True,
        "orderBy": "startTime",
    }
    if time_min:
        params["timeMin"] = time_min
    if time_max:
        params["timeMax"] = time_max
    if query:
        params["q"] = query
    resp = with_retry(lambda: svc.events().list(**params).execute())
    items = resp.get("items", []) or []
    return {
        "ok": True,
        "calendar_id": calendar_id,
        "count": len(items),
        "events": [_event_to_summary(e) for e in items],
    }


_START_DESC = (
    "`YYYY-MM-DD` for an all-day event, or `YYYY-MM-DDTHH:MM[:SS]` for a timed "
    "one (a trailing `±HH:MM`/`Z` offset is honoured; without one the event is "
    "placed in `timezone`, defaulting to the calendar's own)"
)
_END_DESC = (
    "Optional, same shape as `start`. Omit it for a one-day all-day event, or "
    "a timed event of `duration_minutes`."
)
_SEND_UPDATES_DESC = (
    "Who to email. Left unset, an event *with* attendees notifies them "
    "(`all`) and one without notifies nobody (`none`)."
)


@tool(
    name="calendar_create_event",
    feature="calendar.write",
    description=(
        "Create a calendar event, all-day or timed. Pass `start` as "
        "`YYYY-MM-DD` for all-day, or `YYYY-MM-DDTHH:MM` for a timed event — "
        "a bare datetime lands in the calendar's own timezone unless you pass "
        "`timezone`. `end` is optional (one day, or `duration_minutes`). "
        "`attendees` is a list of email strings, and they are emailed by "
        "default; pass `send_updates='none'` to add them silently."
    ),
    input_schema={
        "type": "object",
        "required": ["summary", "start"],
        "properties": {
            "calendar_id": {"type": "string", "default": "primary"},
            "summary": {"type": "string"},
            "description": {"type": "string"},
            "location": {"type": "string"},
            "start": {"type": "string", "description": _START_DESC},
            "end": {"type": "string", "description": _END_DESC},
            "timezone": {
                "type": "string",
                "description": "IANA name, e.g. `America/Chicago`. Only used for "
                "timed events; defaults to the calendar's own timezone.",
            },
            "duration_minutes": {
                "type": "integer",
                "default": DEFAULT_DURATION_MINUTES,
                "minimum": 1,
                "description": "Length of a timed event when `end` is omitted.",
            },
            "attendees": {"type": "array", "items": {"type": "string", "format": "email"}},
            "send_updates": {
                "type": "string",
                "enum": ["all", "externalOnly", "none"],
                "description": _SEND_UPDATES_DESC,
            },
        },
    },
)
def calendar_create_event(
    summary: str,
    start: str,
    end: str | None = None,
    calendar_id: str = "primary",
    description: str | None = None,
    location: str | None = None,
    timezone: str | None = None,
    duration_minutes: int | None = None,
    attendees: list[str] | None = None,
    send_updates: str | None = None,
) -> dict[str, Any]:
    try:
        start_obj, end_obj = _event_times(
            start, end, calendar_id, timezone, duration_minutes
        )
    except _TimeError as exc:
        return error(str(exc))
    body: dict[str, Any] = {"summary": summary, "start": start_obj, "end": end_obj}
    if description:
        body["description"] = description
    if location:
        body["location"] = location
    if attendees:
        body["attendees"] = [{"email": e} for e in attendees]
    send = _resolve_send_updates(send_updates, attendees)
    svc = _svc()
    ev = with_retry(
        lambda: svc.events()
        .insert(calendarId=calendar_id, body=body, sendUpdates=send)
        .execute()
    )
    return {"ok": True, "calendar_id": calendar_id, "notified": send, **_event_to_summary(ev)}


def _clearing(obj: dict[str, str]) -> dict[str, Any]:
    """A patch-safe time object.

    Calendar merges nested objects on patch and rejects an event carrying both
    `date` and `dateTime`, so flipping all-day ↔ timed has to null the old key.
    """
    unused = "date" if "dateTime" in obj else "dateTime"
    return {**obj, unused: None}


def _patched_times(
    event_id: str,
    calendar_id: str,
    start: str | None,
    end: str | None,
    timezone: str | None,
    duration_minutes: int | None,
) -> tuple[dict[str, str], dict[str, str]]:
    """Resolve the start/end pair for a patch, reading the event if one side
    is missing — Calendar validates the pair, not the field you sent."""
    if start is not None and end is not None:
        return _event_times(start, end, calendar_id, timezone, duration_minutes)

    svc = _svc()
    current = with_retry(
        lambda: svc.events().get(calendarId=calendar_id, eventId=event_id).execute()
    )
    cur_start_obj = current.get("start") or {}
    cur_end_obj = current.get("end") or {}
    cur_start = cur_start_obj.get("dateTime") or cur_start_obj.get("date")
    cur_end = cur_end_obj.get("dateTime") or cur_end_obj.get("date")
    if not cur_start:
        raise _TimeError(f"event {event_id} has no start time to patch against")

    if start is None:
        return _event_times(cur_start, end, calendar_id, timezone, duration_minutes)

    # Moving a timed event keeps its length unless the caller says otherwise.
    if (
        duration_minutes is None
        and cur_end
        and not _is_date_only(start)
        and not _is_date_only(cur_start)
    ):
        span = _parse_dt(cur_end, "end") - _parse_dt(cur_start, "start")
        duration_minutes = max(1, round(span.total_seconds() / 60))
    return _event_times(start, None, calendar_id, timezone, duration_minutes)


@tool(
    name="calendar_update_event",
    feature="calendar.write",
    description=(
        "Patch a calendar event. Pass only fields you want to change; the "
        "rest are preserved. `start`/`end` take the same shapes as "
        "`calendar_create_event`, so an event can be flipped between all-day "
        "and timed here; moving only `start` keeps the existing length. Use "
        "`attendees` to *replace* the attendee list (Google's API doesn't "
        "support append semantics here) — replacing it notifies by default."
    ),
    input_schema={
        "type": "object",
        "required": ["event_id"],
        "properties": {
            "calendar_id": {"type": "string", "default": "primary"},
            "event_id": {"type": "string"},
            "summary": {"type": "string"},
            "description": {"type": "string"},
            "location": {"type": "string"},
            "start": {"type": "string", "description": _START_DESC},
            "end": {"type": "string", "description": _END_DESC},
            "timezone": {
                "type": "string",
                "description": "IANA name; timed events only, defaults to the "
                "calendar's own timezone.",
            },
            "duration_minutes": {
                "type": "integer",
                "minimum": 1,
                "description": "New length for a timed event. Omit to keep the "
                "event's current length.",
            },
            "attendees": {"type": "array", "items": {"type": "string", "format": "email"}},
            "send_updates": {
                "type": "string",
                "enum": ["all", "externalOnly", "none"],
                "description": _SEND_UPDATES_DESC,
            },
        },
    },
)
def calendar_update_event(
    event_id: str,
    calendar_id: str = "primary",
    summary: str | None = None,
    description: str | None = None,
    location: str | None = None,
    start: str | None = None,
    end: str | None = None,
    timezone: str | None = None,
    duration_minutes: int | None = None,
    attendees: list[str] | None = None,
    send_updates: str | None = None,
) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    if summary is not None:
        patch["summary"] = summary
    if description is not None:
        patch["description"] = description
    if location is not None:
        patch["location"] = location
    if start is not None or end is not None:
        try:
            start_obj, end_obj = _patched_times(
                event_id, calendar_id, start, end, timezone, duration_minutes
            )
        except _TimeError as exc:
            return error(str(exc))
        patch["start"] = _clearing(start_obj)
        patch["end"] = _clearing(end_obj)
    if attendees is not None:
        patch["attendees"] = [{"email": e} for e in attendees]
    if not patch:
        return error("no fields provided to update")
    send = _resolve_send_updates(send_updates, attendees)
    svc = _svc()
    ev = with_retry(
        lambda: svc.events()
        .patch(
            calendarId=calendar_id,
            eventId=event_id,
            body=patch,
            sendUpdates=send,
        )
        .execute()
    )
    return {"ok": True, "calendar_id": calendar_id, "notified": send, **_event_to_summary(ev)}


@tool(
    name="calendar_get_event",
    feature="calendar.read",
    description="Fetch a single event by id from a calendar (default `primary`).",
    input_schema={
        "type": "object",
        "required": ["event_id"],
        "properties": {
            "calendar_id": {"type": "string", "default": "primary"},
            "event_id": {"type": "string"},
        },
    },
)
def calendar_get_event(event_id: str, calendar_id: str = "primary") -> dict[str, Any]:
    svc = _svc()
    ev = with_retry(
        lambda: svc.events().get(calendarId=calendar_id, eventId=event_id).execute()
    )
    return {"ok": True, "calendar_id": calendar_id, **_event_to_summary(ev)}


@tool(
    name="calendar_list_calendars",
    feature="calendar.read",
    description=(
        "List the calendars on the user's calendar list (id, summary, whether "
        "it's `primary`, and the user's `accessRole`). Use this to resolve a "
        "`calendar_id` for the other calendar tools."
    ),
    input_schema={"type": "object", "properties": {}},
)
def calendar_list_calendars() -> dict[str, Any]:
    svc = _svc()
    resp = with_retry(lambda: svc.calendarList().list().execute())
    items = resp.get("items", []) or []
    return {
        "ok": True,
        "count": len(items),
        "calendars": [
            {
                "id": c.get("id"),
                "summary": c.get("summary"),
                "primary": c.get("primary", False),
                "access_role": c.get("accessRole"),
            }
            for c in items
        ],
    }


@tool(
    name="calendar_delete_event",
    feature="calendar.write",
    description=(
        "Delete (cancel) an event by id. Set `send_updates='all'` to notify "
        "attendees of the cancellation; default `'none'`."
    ),
    input_schema={
        "type": "object",
        "required": ["event_id"],
        "properties": {
            "calendar_id": {"type": "string", "default": "primary"},
            "event_id": {"type": "string"},
            "send_updates": {
                "type": "string",
                "enum": ["all", "externalOnly", "none"],
                "default": "none",
            },
        },
    },
)
def calendar_delete_event(
    event_id: str, calendar_id: str = "primary", send_updates: str = "none"
) -> dict[str, Any]:
    svc = _svc()
    with_retry(
        lambda: svc.events()
        .delete(calendarId=calendar_id, eventId=event_id, sendUpdates=send_updates)
        .execute()
    )
    return {"ok": True, "calendar_id": calendar_id, "event_id": event_id, "deleted": True}


@tool(
    name="calendar_respond_to_event",
    feature="calendar.write",
    description=(
        "RSVP to an event you're invited to: set your own attendee response to "
        "`accepted`, `declined`, or `tentative`. Only your attendee entry is "
        "changed. Errors if you're not on the attendee list."
    ),
    input_schema={
        "type": "object",
        "required": ["event_id", "response"],
        "properties": {
            "calendar_id": {"type": "string", "default": "primary"},
            "event_id": {"type": "string"},
            "response": {
                "type": "string",
                "enum": ["accepted", "declined", "tentative"],
            },
            "send_updates": {
                "type": "string",
                "enum": ["all", "externalOnly", "none"],
                "default": "all",
            },
        },
    },
)
def calendar_respond_to_event(
    event_id: str,
    response: str,
    calendar_id: str = "primary",
    send_updates: str = "all",
) -> dict[str, Any]:
    svc = _svc()
    ev = with_retry(
        lambda: svc.events().get(calendarId=calendar_id, eventId=event_id).execute()
    )
    attendees = ev.get("attendees", []) or []
    me = next((a for a in attendees if a.get("self")), None)
    if me is None:
        return error("you are not an attendee of this event — cannot RSVP")
    me["responseStatus"] = response
    updated = with_retry(
        lambda: svc.events()
        .patch(
            calendarId=calendar_id,
            eventId=event_id,
            body={"attendees": attendees},
            sendUpdates=send_updates,
        )
        .execute()
    )
    return {"ok": True, "calendar_id": calendar_id, "response": response, **_event_to_summary(updated)}
