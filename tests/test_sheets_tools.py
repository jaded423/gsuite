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
