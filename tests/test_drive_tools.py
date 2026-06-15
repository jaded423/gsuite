"""Tests for the Drive tool handlers.

Each test injects a MagicMock service and asserts the *shape* of the Drive
API calls — the query sent to `files.list`, the body sent to `files.create`,
the parent-swap args on `files.update`. No real API, no credentials needed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from gsuite.tools import drive_common, drive_tools


@pytest.fixture(autouse=True)
def _no_folder_cache():
    drive_common.reset_folder_cache()
    yield
    drive_common.reset_folder_cache()


@pytest.fixture
def fake_svc(monkeypatch):
    svc = MagicMock()
    monkeypatch.setattr(drive_tools, "_svc", lambda: svc)
    monkeypatch.setattr(drive_common, "build_drive", lambda: svc)
    return svc


def _list_returns(svc, payload):
    svc.files.return_value.list.return_value.execute.return_value = payload


def _get_returns(svc, payload):
    svc.files.return_value.get.return_value.execute.return_value = payload


def _update_returns(svc, payload):
    svc.files.return_value.update.return_value.execute.return_value = payload


def _create_returns(svc, payload):
    svc.files.return_value.create.return_value.execute.return_value = payload


def _permissions_create_returns(svc, payload):
    svc.permissions.return_value.create.return_value.execute.return_value = payload


# --- drive_search ------------------------------------------------------------

def test_search_passes_query_through(fake_svc):
    _list_returns(fake_svc, {"files": [{"id": "A", "name": "a"}]})
    out = drive_tools.drive_search("name contains 'x'", limit=10)
    assert out["ok"] is True
    assert out["count"] == 1
    kwargs = fake_svc.files.return_value.list.call_args.kwargs
    assert kwargs["q"] == "name contains 'x'"
    assert kwargs["pageSize"] == 10


def test_search_caps_page_size_at_100(fake_svc):
    _list_returns(fake_svc, {"files": []})
    drive_tools.drive_search("x", limit=500)
    assert fake_svc.files.return_value.list.call_args.kwargs["pageSize"] == 100


def test_search_includes_shared_drives(fake_svc):
    _list_returns(fake_svc, {"files": []})
    drive_tools.drive_search("x")
    kwargs = fake_svc.files.return_value.list.call_args.kwargs
    assert kwargs["includeItemsFromAllDrives"] is True
    assert kwargs["supportsAllDrives"] is True
    assert kwargs["corpora"] == "allDrives"


def test_list_folder_includes_shared_drives(fake_svc):
    _list_returns(fake_svc, {"files": []})
    drive_tools.drive_list_folder(folder_id="F")
    kwargs = fake_svc.files.return_value.list.call_args.kwargs
    assert kwargs["includeItemsFromAllDrives"] is True
    assert kwargs["supportsAllDrives"] is True
    assert kwargs["corpora"] == "allDrives"


# --- drive_get_metadata -----------------------------------------------------

def test_get_metadata_returns_file_fields(fake_svc):
    fake_svc.files.return_value.get.return_value.execute.return_value = {
        "id": "F", "name": "n", "mimeType": "m", "parents": ["P"], "driveId": "D",
    }
    out = drive_tools.drive_get_metadata("F")
    assert out["ok"] is True
    assert out["name"] == "n"
    assert out["driveId"] == "D"
    kwargs = fake_svc.files.return_value.get.call_args.kwargs
    assert kwargs["fileId"] == "F"
    assert kwargs["supportsAllDrives"] is True


# --- drive_list_folder -------------------------------------------------------

def test_list_folder_defaults_to_root(fake_svc):
    _list_returns(fake_svc, {"files": []})
    drive_tools.drive_list_folder()
    q = fake_svc.files.return_value.list.call_args.kwargs["q"]
    assert "'root' in parents" in q
    assert "trashed = false" in q


def test_list_folder_scopes_to_given_folder(fake_svc):
    _list_returns(fake_svc, {"files": []})
    drive_tools.drive_list_folder(folder_id="ABC123")
    q = fake_svc.files.return_value.list.call_args.kwargs["q"]
    assert "'ABC123' in parents" in q


# --- drive_create_folder -----------------------------------------------------

def test_create_folder_defaults_parent_to_root(fake_svc):
    _create_returns(fake_svc, {"id": "F1", "name": "proj", "parents": ["root"]})
    out = drive_tools.drive_create_folder("proj")
    assert out["ok"] is True
    body = fake_svc.files.return_value.create.call_args.kwargs["body"]
    assert body == {
        "name": "proj",
        "mimeType": drive_common.FOLDER_MIME,
        "parents": ["root"],
    }


def test_create_folder_nests_under_parent(fake_svc):
    _create_returns(fake_svc, {"id": "F2", "name": "sub", "parents": ["P"]})
    drive_tools.drive_create_folder("sub", parent_id="P")
    body = fake_svc.files.return_value.create.call_args.kwargs["body"]
    assert body["parents"] == ["P"]


# --- drive_rename ------------------------------------------------------------

def test_rename_sends_name_only(fake_svc):
    _update_returns(fake_svc, {"id": "X", "name": "new.doc"})
    out = drive_tools.drive_rename("X", "new.doc")
    assert out["name"] == "new.doc"
    kwargs = fake_svc.files.return_value.update.call_args.kwargs
    assert kwargs["body"] == {"name": "new.doc"}


# --- drive_move --------------------------------------------------------------

def test_move_swaps_parents(fake_svc):
    _get_returns(fake_svc, {"id": "F", "name": "x", "parents": ["OLD"]})
    _update_returns(fake_svc, {"id": "F", "name": "x", "parents": ["NEW"]})
    out = drive_tools.drive_move("F", "NEW")
    assert out["previous_parents"] == ["OLD"]
    kwargs = fake_svc.files.return_value.update.call_args.kwargs
    assert kwargs["addParents"] == "NEW"
    assert kwargs["removeParents"] == "OLD"


def test_move_is_noop_when_already_in_target(fake_svc):
    _get_returns(fake_svc, {"id": "F", "name": "x", "parents": ["NEW"]})
    out = drive_tools.drive_move("F", "NEW")
    assert out["unchanged"] is True
    fake_svc.files.return_value.update.assert_not_called()


# --- drive_share -------------------------------------------------------------

def test_share_rejects_unknown_role(fake_svc):
    out = drive_tools.drive_share("F", "a@b.com", role="owner")
    assert out["ok"] is False
    assert out["retryable"] is False


def test_share_creates_permission(fake_svc):
    _permissions_create_returns(fake_svc, {"id": "P1", "role": "reader", "emailAddress": "a@b.com"})
    out = drive_tools.drive_share("F", "a@b.com", role="reader", notify=True)
    assert out["ok"] is True
    kwargs = fake_svc.permissions.return_value.create.call_args.kwargs
    assert kwargs["fileId"] == "F"
    assert kwargs["body"] == {"type": "user", "role": "reader", "emailAddress": "a@b.com"}
    assert kwargs["sendNotificationEmail"] is True


# --- drive_soft_delete + drive_list_delete_later ----------------------------

def test_soft_delete_routes_through_drive_common(fake_svc):
    # folder lookup returns existing folder, then file metadata returned,
    # then update returns new parents.
    svc = fake_svc
    svc.files.return_value.list.return_value.execute.return_value = {
        "files": [{"id": "TRASH", "name": "_delete-later"}]
    }
    _get_returns(svc, {"id": "X", "name": "doomed", "parents": ["P"]})
    _update_returns(svc, {"id": "X", "name": "doomed", "parents": ["TRASH"]})

    out = drive_tools.drive_soft_delete("X")
    assert out["ok"] is True
    assert out["already_pending"] is False
    # Crucially: no files().delete() ever called.
    svc.files.return_value.delete.assert_not_called()


def test_list_delete_later_tool_lists_folder(fake_svc):
    svc = fake_svc
    # First list call → folder lookup; second → files in folder.
    svc.files.return_value.list.return_value.execute.side_effect = [
        {"files": [{"id": "TRASH"}]},
        {"files": [{"id": "A"}, {"id": "B"}]},
    ]
    out = drive_tools.drive_list_delete_later()
    assert out["ok"] is True
    assert out["count"] == 2
