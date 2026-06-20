"""Tests for Google Sheets tools."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gsuite.tools import sheets_tools


@pytest.fixture
def fake_svc(monkeypatch):
    svc = MagicMock()
    monkeypatch.setattr(sheets_tools, "_svc", lambda: svc)
    return svc


def test_read_range_returns_rows(fake_svc):
    fake_svc.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
        "range": "Sheet1!A1:B2",
        "values": [["a", "b"], ["c", "d"]],
    }
    out = sheets_tools.sheets_read_range("SID", "Sheet1!A1:B2")
    assert out["rows"] == 2
    assert out["values"] == [["a", "b"], ["c", "d"]]


def test_append_rows_defaults_to_user_entered(fake_svc):
    fake_svc.spreadsheets.return_value.values.return_value.append.return_value.execute.return_value = {
        "updates": {"updatedRows": 1, "updatedCells": 2, "updatedRange": "Sheet1!A5:B5"}
    }
    out = sheets_tools.sheets_append_rows("SID", "Sheet1!A:B", [["a", "b"]])
    assert out["updated_rows"] == 1
    kwargs = fake_svc.spreadsheets.return_value.values.return_value.append.call_args.kwargs
    assert kwargs["valueInputOption"] == "USER_ENTERED"
    assert kwargs["body"] == {"values": [["a", "b"]]}


def test_append_rows_rejects_empty_rows():
    out = sheets_tools.sheets_append_rows("SID", "Sheet1!A:A", [])
    assert out["ok"] is False


def test_append_rows_rejects_bad_input_option():
    out = sheets_tools.sheets_append_rows("SID", "A:A", [["x"]], input_option="BOGUS")
    assert out["ok"] is False


def test_update_range_writes_values(fake_svc):
    fake_svc.spreadsheets.return_value.values.return_value.update.return_value.execute.return_value = {
        "updatedRange": "Sheet1!A1:B1", "updatedRows": 1, "updatedCells": 2
    }
    out = sheets_tools.sheets_update_range("SID", "Sheet1!A1:B1", [["x", "y"]])
    assert out["updated_cells"] == 2
    kwargs = fake_svc.spreadsheets.return_value.values.return_value.update.call_args.kwargs
    assert kwargs["body"] == {"values": [["x", "y"]]}


def test_create_returns_url(fake_svc):
    fake_svc.spreadsheets.return_value.create.return_value.execute.return_value = {
        "spreadsheetId": "SID_NEW"
    }
    out = sheets_tools.sheets_create("Q2 Metrics")
    assert out["spreadsheet_id"] == "SID_NEW"
    assert "SID_NEW" in out["url"]


def test_add_sheet_returns_new_gid(fake_svc):
    fake_svc.spreadsheets.return_value.batchUpdate.return_value.execute.return_value = {
        "replies": [{"addSheet": {"properties": {"sheetId": 123, "title": "Indica", "index": 1}}}]
    }
    out = sheets_tools.sheets_add_sheet("SID", "Indica")
    assert out["ok"] is True
    assert out["sheet_id"] == 123
    body = fake_svc.spreadsheets.return_value.batchUpdate.call_args.kwargs["body"]
    assert body["requests"][0]["addSheet"]["properties"]["title"] == "Indica"


def test_add_sheet_passes_index(fake_svc):
    fake_svc.spreadsheets.return_value.batchUpdate.return_value.execute.return_value = {
        "replies": [{"addSheet": {"properties": {"sheetId": 5, "title": "T", "index": 2}}}]
    }
    sheets_tools.sheets_add_sheet("SID", "T", index=2)
    props = fake_svc.spreadsheets.return_value.batchUpdate.call_args.kwargs["body"][
        "requests"
    ][0]["addSheet"]["properties"]
    assert props["index"] == 2


def test_add_sheet_rejects_empty_title():
    assert sheets_tools.sheets_add_sheet("SID", "")["ok"] is False


def _stub_list(fake_svc, sheets):
    fake_svc.spreadsheets.return_value.get.return_value.execute.return_value = {
        "sheets": [{"properties": p} for p in sheets]
    }


def test_rename_sheet_by_sheet_id(fake_svc):
    fake_svc.spreadsheets.return_value.batchUpdate.return_value.execute.return_value = {}
    out = sheets_tools.sheets_rename_sheet("SID", "New", sheet_id=7)
    assert out["sheet_id"] == 7 and out["title"] == "New"
    req = fake_svc.spreadsheets.return_value.batchUpdate.call_args.kwargs["body"][
        "requests"
    ][0]["updateSheetProperties"]
    assert req["properties"] == {"sheetId": 7, "title": "New"}
    assert req["fields"] == "title"


def test_rename_sheet_resolves_title(fake_svc):
    _stub_list(fake_svc, [{"sheetId": 0, "title": "A", "index": 0}, {"sheetId": 9, "title": "B", "index": 1}])
    fake_svc.spreadsheets.return_value.batchUpdate.return_value.execute.return_value = {}
    out = sheets_tools.sheets_rename_sheet("SID", "C", title="B")
    assert out["sheet_id"] == 9


def test_rename_sheet_unknown_title_errors(fake_svc):
    _stub_list(fake_svc, [{"sheetId": 0, "title": "A", "index": 0}])
    out = sheets_tools.sheets_rename_sheet("SID", "C", title="Nope")
    assert out["ok"] is False


def test_rename_sheet_needs_identifier(fake_svc):
    out = sheets_tools.sheets_rename_sheet("SID", "C")
    assert out["ok"] is False


def test_delete_sheet_by_gid(fake_svc):
    fake_svc.spreadsheets.return_value.batchUpdate.return_value.execute.return_value = {}
    out = sheets_tools.sheets_delete_sheet("SID", sheet_id=4)
    assert out["deleted_sheet_id"] == 4
    req = fake_svc.spreadsheets.return_value.batchUpdate.call_args.kwargs["body"][
        "requests"
    ][0]["deleteSheet"]
    assert req["sheetId"] == 4


def test_delete_sheet_ambiguous_title_errors(fake_svc):
    _stub_list(fake_svc, [{"sheetId": 1, "title": "Dup", "index": 0}, {"sheetId": 2, "title": "Dup", "index": 1}])
    out = sheets_tools.sheets_delete_sheet("SID", title="Dup")
    assert out["ok"] is False
