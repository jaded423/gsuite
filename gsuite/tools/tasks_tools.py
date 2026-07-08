"""Google Tasks tools — list task lists, list/create/update/delete tasks.

The Tasks API models a user's to-dos as *tasks* inside *task lists*. Every
account has a built-in default list reachable by the special id `@default`,
which every tool here uses when no `tasklist` is given.

`due` is an RFC 3339 timestamp, but Google only stores and honors the **date**
portion (no time-of-day on a task). Pass e.g. `2026-07-10T00:00:00Z`; the API
echoes it back at midnight UTC. Tasks with no `due` are "dateless" — the shape
the meeting→action-items pipeline routes here so they surface in Calendar's
sidebar without pinning a time.

Completion is a status flip, not a delete: set `status='completed'` (or pass
`completed=True` to `tasks_update`) and Google stamps the completion time and
hides the task from the default list view. `show_completed=True` on
`tasks_list` brings them back.

All tools share the single `tasks` feature flag (scope
`https://www.googleapis.com/auth/tasks`), already staged on the consent screen
— no re-consent to enable.
"""

from __future__ import annotations

import logging
from typing import Any

from ..auth import build_service, with_retry
from ._errors import error
from ._registry import tool

log = logging.getLogger("gsuite.tools.tasks")

# The API accepts this alias anywhere a tasklist id is expected.
DEFAULT_TASKLIST = "@default"


def _svc():
    return build_service("tasks")


def _task_to_summary(t: dict[str, Any]) -> dict[str, Any]:
    """Flatten a Tasks task resource to the fields we care about."""
    return {
        "id": t.get("id"),
        "title": t.get("title"),
        "notes": t.get("notes"),
        "status": t.get("status"),
        "due": t.get("due"),
        "completed": t.get("completed"),
        "parent": t.get("parent"),
        "position": t.get("position"),
        "updated": t.get("updated"),
    }


def _tasklist_to_summary(tl: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": tl.get("id"),
        "title": tl.get("title"),
        "updated": tl.get("updated"),
    }


@tool(
    name="tasklists_list",
    feature="tasks",
    description=(
        "List the authenticated user's task lists (id + title). Use this to "
        "discover the `tasklist` id for the other tasks tools; the built-in "
        "default list is also always reachable as `@default`."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "max_results": {"type": "integer", "default": 100, "minimum": 1, "maximum": 100},
        },
    },
)
def tasklists_list(max_results: int = 100) -> dict[str, Any]:
    svc = _svc()
    resp = with_retry(lambda: svc.tasklists().list(maxResults=max_results).execute())
    items = resp.get("items", []) or []
    return {
        "ok": True,
        "count": len(items),
        "tasklists": [_tasklist_to_summary(t) for t in items],
    }


@tool(
    name="tasks_list",
    feature="tasks",
    description=(
        "List tasks in a task list (default `@default`). Completed tasks are "
        "hidden unless `show_completed=True`. Tasks are returned in the list's "
        "own order (`position`)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "tasklist": {"type": "string", "default": DEFAULT_TASKLIST},
            "show_completed": {"type": "boolean", "default": False},
            "max_results": {"type": "integer", "default": 100, "minimum": 1, "maximum": 100},
        },
    },
)
def tasks_list(
    tasklist: str = DEFAULT_TASKLIST,
    show_completed: bool = False,
    max_results: int = 100,
) -> dict[str, Any]:
    svc = _svc()
    params: dict[str, Any] = {
        "tasklist": tasklist,
        "maxResults": max_results,
        "showCompleted": show_completed,
    }
    # Completed tasks are also flagged hidden; must opt into both to see them.
    if show_completed:
        params["showHidden"] = True
    resp = with_retry(lambda: svc.tasks().list(**params).execute())
    items = resp.get("items", []) or []
    return {
        "ok": True,
        "tasklist": tasklist,
        "count": len(items),
        "tasks": [_task_to_summary(t) for t in items],
    }


@tool(
    name="tasks_create",
    feature="tasks",
    description=(
        "Create a task in a task list (default `@default`). `due` is RFC 3339 "
        "but only the date is honored (no time-of-day). Omit `due` for a "
        "dateless action item. Set `parent` to a task id to nest this as a "
        "subtask."
    ),
    input_schema={
        "type": "object",
        "required": ["title"],
        "properties": {
            "title": {"type": "string"},
            "tasklist": {"type": "string", "default": DEFAULT_TASKLIST},
            "notes": {"type": "string"},
            "due": {"type": "string", "description": "RFC 3339; date honored, time ignored"},
            "parent": {"type": "string", "description": "Parent task id for a subtask"},
        },
    },
)
def tasks_create(
    title: str,
    tasklist: str = DEFAULT_TASKLIST,
    notes: str | None = None,
    due: str | None = None,
    parent: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"title": title}
    if notes is not None:
        body["notes"] = notes
    if due is not None:
        body["due"] = due
    svc = _svc()
    params: dict[str, Any] = {"tasklist": tasklist, "body": body}
    if parent:
        params["parent"] = parent
    t = with_retry(lambda: svc.tasks().insert(**params).execute())
    return {"ok": True, "tasklist": tasklist, **_task_to_summary(t)}


@tool(
    name="tasks_update",
    feature="tasks",
    description=(
        "Patch a task. Pass only the fields you want to change; the rest are "
        "preserved. `completed=True` marks it done (status→completed); "
        "`completed=False` reopens it (status→needsAction). Pass `due=''` to "
        "clear the due date. `completed` and an explicit `status` are mutually "
        "exclusive."
    ),
    input_schema={
        "type": "object",
        "required": ["task_id"],
        "properties": {
            "task_id": {"type": "string"},
            "tasklist": {"type": "string", "default": DEFAULT_TASKLIST},
            "title": {"type": "string"},
            "notes": {"type": "string"},
            "due": {"type": "string", "description": "RFC 3339; empty string clears it"},
            "status": {"type": "string", "enum": ["needsAction", "completed"]},
            "completed": {"type": "boolean", "description": "Shortcut for status"},
        },
    },
)
def tasks_update(
    task_id: str,
    tasklist: str = DEFAULT_TASKLIST,
    title: str | None = None,
    notes: str | None = None,
    due: str | None = None,
    status: str | None = None,
    completed: bool | None = None,
) -> dict[str, Any]:
    if completed is not None and status is not None:
        return error("pass either `completed` or `status`, not both")
    patch: dict[str, Any] = {}
    if title is not None:
        patch["title"] = title
    if notes is not None:
        patch["notes"] = notes
    if due is not None:
        # Empty string clears the due date; Google needs an explicit null.
        patch["due"] = due if due else None
    if completed is not None:
        status = "completed" if completed else "needsAction"
    if status is not None:
        patch["status"] = status
        # Reopening must clear the stored completion timestamp, else the API
        # keeps the task marked done.
        if status == "needsAction":
            patch["completed"] = None
    if not patch:
        return error("no fields provided to update")
    svc = _svc()
    t = with_retry(
        lambda: svc.tasks().patch(tasklist=tasklist, task=task_id, body=patch).execute()
    )
    return {"ok": True, "tasklist": tasklist, **_task_to_summary(t)}


@tool(
    name="tasks_delete",
    feature="tasks",
    description=(
        "Delete a task from a task list (default `@default`). This removes it "
        "outright — to merely mark it done, use `tasks_update` with "
        "`completed=True` instead."
    ),
    input_schema={
        "type": "object",
        "required": ["task_id"],
        "properties": {
            "task_id": {"type": "string"},
            "tasklist": {"type": "string", "default": DEFAULT_TASKLIST},
        },
    },
)
def tasks_delete(task_id: str, tasklist: str = DEFAULT_TASKLIST) -> dict[str, Any]:
    svc = _svc()
    with_retry(lambda: svc.tasks().delete(tasklist=tasklist, task=task_id).execute())
    return {"ok": True, "tasklist": tasklist, "task_id": task_id, "deleted": True}
