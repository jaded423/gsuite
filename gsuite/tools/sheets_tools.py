"""Google Sheets tools — read range, append rows, update range, create,
plus per-tab add/rename/delete.

Value input option defaults to `USER_ENTERED` so formulas and auto-typed
numbers behave as they would in the UI. Raw-string writes are still possible
via `input_option='RAW'` on the write tools.
"""

from __future__ import annotations

import logging
from typing import Any

from ..auth import build_service, with_retry
from ._errors import error
from ._registry import tool

log = logging.getLogger("gsuite.tools.sheets")

VALID_INPUT_OPTIONS = {"USER_ENTERED", "RAW"}


def _svc():
    return build_service("sheets")


@tool(
    name="sheets_read_range",
    feature="sheets.read",
    description=(
        "Read a range from a spreadsheet (A1 notation, e.g. 'Sheet1!A1:C50'). "
        "Returns `values` as a list of rows. Empty trailing cells are omitted."
    ),
    input_schema={
        "type": "object",
        "required": ["spreadsheet_id", "range"],
        "properties": {
            "spreadsheet_id": {"type": "string"},
            "range": {"type": "string"},
        },
    },
)
def sheets_read_range(spreadsheet_id: str, range: str) -> dict[str, Any]:
    svc = _svc()
    resp = with_retry(
        lambda: svc.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=range)
        .execute()
    )
    values = resp.get("values", []) or []
    return {
        "ok": True,
        "spreadsheet_id": spreadsheet_id,
        "range": resp.get("range", range),
        "rows": len(values),
        "values": values,
    }


@tool(
    name="sheets_append_rows",
    feature="sheets.write",
    description=(
        "Append rows to the bottom of a range (A1 notation). `rows` is a list "
        "of lists. Default input option `USER_ENTERED` interprets formulas "
        "and auto-types numbers like the UI; pass `RAW` to store as-is."
    ),
    input_schema={
        "type": "object",
        "required": ["spreadsheet_id", "range", "rows"],
        "properties": {
            "spreadsheet_id": {"type": "string"},
            "range": {"type": "string"},
            "rows": {
                "type": "array",
                "items": {"type": "array", "items": {}},
            },
            "input_option": {
                "type": "string",
                "enum": ["USER_ENTERED", "RAW"],
                "default": "USER_ENTERED",
            },
        },
    },
)
def sheets_append_rows(
    spreadsheet_id: str,
    range: str,
    rows: list[list[Any]],
    input_option: str = "USER_ENTERED",
) -> dict[str, Any]:
    if input_option not in VALID_INPUT_OPTIONS:
        return error(f"invalid input_option {input_option!r}")
    if not rows:
        return error("rows is required")
    svc = _svc()
    resp = with_retry(
        lambda: svc.spreadsheets()
        .values()
        .append(
            spreadsheetId=spreadsheet_id,
            range=range,
            valueInputOption=input_option,
            insertDataOption="INSERT_ROWS",
            body={"values": rows},
        )
        .execute()
    )
    updates = resp.get("updates", {}) or {}
    return {
        "ok": True,
        "spreadsheet_id": spreadsheet_id,
        "updated_range": updates.get("updatedRange"),
        "updated_rows": updates.get("updatedRows", 0),
        "updated_cells": updates.get("updatedCells", 0),
    }


@tool(
    name="sheets_update_range",
    feature="sheets.write",
    description=(
        "Write `values` into a specific A1 range, overwriting existing cells. "
        "Use for fixed-position data; use `sheets_append_rows` for growing logs."
    ),
    input_schema={
        "type": "object",
        "required": ["spreadsheet_id", "range", "values"],
        "properties": {
            "spreadsheet_id": {"type": "string"},
            "range": {"type": "string"},
            "values": {
                "type": "array",
                "items": {"type": "array", "items": {}},
            },
            "input_option": {
                "type": "string",
                "enum": ["USER_ENTERED", "RAW"],
                "default": "USER_ENTERED",
            },
        },
    },
)
def sheets_update_range(
    spreadsheet_id: str,
    range: str,
    values: list[list[Any]],
    input_option: str = "USER_ENTERED",
) -> dict[str, Any]:
    if input_option not in VALID_INPUT_OPTIONS:
        return error(f"invalid input_option {input_option!r}")
    svc = _svc()
    resp = with_retry(
        lambda: svc.spreadsheets()
        .values()
        .update(
            spreadsheetId=spreadsheet_id,
            range=range,
            valueInputOption=input_option,
            body={"values": values},
        )
        .execute()
    )
    return {
        "ok": True,
        "spreadsheet_id": spreadsheet_id,
        "updated_range": resp.get("updatedRange"),
        "updated_rows": resp.get("updatedRows", 0),
        "updated_cells": resp.get("updatedCells", 0),
    }


@tool(
    name="sheets_create",
    feature="sheets.write",
    description="Create a new spreadsheet with the given title. Returns ID and URL.",
    input_schema={
        "type": "object",
        "required": ["title"],
        "properties": {"title": {"type": "string"}},
    },
)
def sheets_create(title: str) -> dict[str, Any]:
    svc = _svc()
    created = with_retry(
        lambda: svc.spreadsheets().create(body={"properties": {"title": title}}).execute()
    )
    sid = created["spreadsheetId"]
    return {
        "ok": True,
        "spreadsheet_id": sid,
        "title": title,
        "url": f"https://docs.google.com/spreadsheets/d/{sid}/edit",
    }


def _list_sheets(svc, spreadsheet_id: str) -> list[dict[str, Any]]:
    """Return [{sheet_id, title, index}, …] for every tab in the spreadsheet."""
    meta = with_retry(
        lambda: svc.spreadsheets()
        .get(spreadsheetId=spreadsheet_id, fields="sheets.properties")
        .execute()
    )
    out = []
    for s in meta.get("sheets", []) or []:
        p = s.get("properties", {}) or {}
        out.append(
            {"sheet_id": p.get("sheetId"), "title": p.get("title"), "index": p.get("index")}
        )
    return out


def _resolve_sheet_id(
    svc, spreadsheet_id: str, sheet_id: int | None, title: str | None
) -> int | str:
    """Resolve a tab to its numeric gid. Returns the gid, or an error string.

    Pass `sheet_id` directly, or `title` to look it up. Title match is exact.
    """
    if sheet_id is not None:
        return sheet_id
    if not title:
        return "provide sheet_id or title"
    matches = [s for s in _list_sheets(svc, spreadsheet_id) if s["title"] == title]
    if not matches:
        return f"no tab titled {title!r}"
    if len(matches) > 1:
        return f"multiple tabs titled {title!r}; pass sheet_id"
    return matches[0]["sheet_id"]


@tool(
    name="sheets_add_sheet",
    feature="sheets.write",
    description=(
        "Add a new tab (sheet) to an existing spreadsheet. Returns the new tab's "
        "`sheet_id` (gid) and title. Use `sheets_create` instead to make a whole "
        "new spreadsheet."
    ),
    input_schema={
        "type": "object",
        "required": ["spreadsheet_id", "title"],
        "properties": {
            "spreadsheet_id": {"type": "string"},
            "title": {"type": "string", "description": "Title for the new tab."},
            "index": {
                "type": "integer",
                "description": "Optional 0-based position among existing tabs.",
            },
        },
    },
)
def sheets_add_sheet(
    spreadsheet_id: str, title: str, index: int | None = None
) -> dict[str, Any]:
    if not title:
        return error("title is required")
    props: dict[str, Any] = {"title": title}
    if index is not None:
        props["index"] = index
    svc = _svc()
    resp = with_retry(
        lambda: svc.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": props}}]},
        )
        .execute()
    )
    added = (resp.get("replies", [{}])[0].get("addSheet", {}) or {}).get("properties", {})
    return {
        "ok": True,
        "spreadsheet_id": spreadsheet_id,
        "sheet_id": added.get("sheetId"),
        "title": added.get("title", title),
        "index": added.get("index"),
    }


@tool(
    name="sheets_rename_sheet",
    feature="sheets.write",
    description=(
        "Rename a tab within a spreadsheet. Identify the tab by `sheet_id` (gid) "
        "or by its current `title`."
    ),
    input_schema={
        "type": "object",
        "required": ["spreadsheet_id", "new_title"],
        "properties": {
            "spreadsheet_id": {"type": "string"},
            "new_title": {"type": "string"},
            "sheet_id": {"type": "integer", "description": "Tab gid."},
            "title": {"type": "string", "description": "Current tab title (if no sheet_id)."},
        },
    },
)
def sheets_rename_sheet(
    spreadsheet_id: str,
    new_title: str,
    sheet_id: int | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    if not new_title:
        return error("new_title is required")
    svc = _svc()
    gid = _resolve_sheet_id(svc, spreadsheet_id, sheet_id, title)
    if isinstance(gid, str):
        return error(gid)
    with_retry(
        lambda: svc.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "updateSheetProperties": {
                            "properties": {"sheetId": gid, "title": new_title},
                            "fields": "title",
                        }
                    }
                ]
            },
        )
        .execute()
    )
    return {"ok": True, "spreadsheet_id": spreadsheet_id, "sheet_id": gid, "title": new_title}


@tool(
    name="sheets_delete_sheet",
    feature="sheets.write",
    description=(
        "Delete a tab from a spreadsheet. Identify the tab by `sheet_id` (gid) or "
        "by `title`. A spreadsheet must keep at least one tab — deleting the last "
        "one fails at the API."
    ),
    input_schema={
        "type": "object",
        "required": ["spreadsheet_id"],
        "properties": {
            "spreadsheet_id": {"type": "string"},
            "sheet_id": {"type": "integer", "description": "Tab gid."},
            "title": {"type": "string", "description": "Tab title (if no sheet_id)."},
        },
    },
)
def sheets_delete_sheet(
    spreadsheet_id: str, sheet_id: int | None = None, title: str | None = None
) -> dict[str, Any]:
    svc = _svc()
    gid = _resolve_sheet_id(svc, spreadsheet_id, sheet_id, title)
    if isinstance(gid, str):
        return error(gid)
    with_retry(
        lambda: svc.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"deleteSheet": {"sheetId": gid}}]},
        )
        .execute()
    )
    return {"ok": True, "spreadsheet_id": spreadsheet_id, "deleted_sheet_id": gid}
