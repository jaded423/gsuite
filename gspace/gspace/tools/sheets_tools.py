"""Google Sheets tools — read range, append rows, update range, create.

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

log = logging.getLogger("gspace.tools.sheets")

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
