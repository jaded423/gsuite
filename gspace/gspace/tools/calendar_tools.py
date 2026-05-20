"""Google Calendar tools — list events, create event, update event.

All timestamps are ISO 8601 with timezone (e.g. `2026-04-17T14:00:00-05:00`).
The tools don't try to parse natural-language times — the MCP client is
expected to resolve relative expressions before calling in.

Default calendar is `primary`, which resolves to the authenticated user's
main calendar.
"""

from __future__ import annotations

import logging
from typing import Any

from ..auth import build_service, with_retry
from ._errors import error
from ._registry import tool

log = logging.getLogger("gspace.tools.calendar")


def _svc():
    return build_service("calendar")


def _event_to_summary(ev: dict[str, Any]) -> dict[str, Any]:
    """Flatten a Calendar event to the fields we care about."""
    return {
        "id": ev.get("id"),
        "summary": ev.get("summary"),
        "description": ev.get("description"),
        "location": ev.get("location"),
        "start": (ev.get("start") or {}).get("dateTime") or (ev.get("start") or {}).get("date"),
        "end": (ev.get("end") or {}).get("dateTime") or (ev.get("end") or {}).get("date"),
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


@tool(
    name="calendar_create_event",
    feature="calendar.write",
    description=(
        "Create a calendar event. `start` and `end` are ISO 8601 timestamps "
        "with timezone. `attendees` is a list of email strings. Set "
        "`send_updates='all'` to email attendees; default `'none'`."
    ),
    input_schema={
        "type": "object",
        "required": ["summary", "start", "end"],
        "properties": {
            "calendar_id": {"type": "string", "default": "primary"},
            "summary": {"type": "string"},
            "description": {"type": "string"},
            "location": {"type": "string"},
            "start": {"type": "string", "description": "ISO 8601 with TZ"},
            "end": {"type": "string", "description": "ISO 8601 with TZ"},
            "attendees": {"type": "array", "items": {"type": "string", "format": "email"}},
            "send_updates": {
                "type": "string",
                "enum": ["all", "externalOnly", "none"],
                "default": "none",
            },
        },
    },
)
def calendar_create_event(
    summary: str,
    start: str,
    end: str,
    calendar_id: str = "primary",
    description: str | None = None,
    location: str | None = None,
    attendees: list[str] | None = None,
    send_updates: str = "none",
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "summary": summary,
        "start": {"dateTime": start},
        "end": {"dateTime": end},
    }
    if description:
        body["description"] = description
    if location:
        body["location"] = location
    if attendees:
        body["attendees"] = [{"email": e} for e in attendees]
    svc = _svc()
    ev = with_retry(
        lambda: svc.events()
        .insert(calendarId=calendar_id, body=body, sendUpdates=send_updates)
        .execute()
    )
    return {"ok": True, "calendar_id": calendar_id, **_event_to_summary(ev)}


@tool(
    name="calendar_update_event",
    feature="calendar.write",
    description=(
        "Patch a calendar event. Pass only fields you want to change; the "
        "rest are preserved. Use `attendees` to *replace* the attendee list "
        "(Google's API doesn't support append semantics here)."
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
            "start": {"type": "string"},
            "end": {"type": "string"},
            "attendees": {"type": "array", "items": {"type": "string", "format": "email"}},
            "send_updates": {
                "type": "string",
                "enum": ["all", "externalOnly", "none"],
                "default": "none",
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
    attendees: list[str] | None = None,
    send_updates: str = "none",
) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    if summary is not None:
        patch["summary"] = summary
    if description is not None:
        patch["description"] = description
    if location is not None:
        patch["location"] = location
    if start is not None:
        patch["start"] = {"dateTime": start}
    if end is not None:
        patch["end"] = {"dateTime": end}
    if attendees is not None:
        patch["attendees"] = [{"email": e} for e in attendees]
    if not patch:
        return error("no fields provided to update")
    svc = _svc()
    ev = with_retry(
        lambda: svc.events()
        .patch(
            calendarId=calendar_id,
            eventId=event_id,
            body=patch,
            sendUpdates=send_updates,
        )
        .execute()
    )
    return {"ok": True, "calendar_id": calendar_id, **_event_to_summary(ev)}
