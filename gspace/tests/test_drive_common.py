"""Tests for drive_common soft-delete scaffolding.

Google's client library returns a fluent builder — each method returns an
object with an `execute()` method. The tests stub this with MagicMock chains
so no network is needed. We assert the *shape* of the calls we make: the
query used to find the folder, the create body when missing, the parent
swap on update.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gspace.tools import drive_common


@pytest.fixture(autouse=True)
def _clear_cache():
    drive_common.reset_folder_cache()
    yield
    drive_common.reset_folder_cache()


def _fake_drive(folder_find_result=None, create_result=None, get_result=None, update_result=None, list_result=None):
    """Build a MagicMock with the builder chains we actually use."""
    svc = MagicMock()

    # files().list(...).execute()  — used by _find_folder_by_name + list_delete_later
    list_exec = MagicMock()
    list_exec.execute.side_effect = [
        folder_find_result if folder_find_result is not None else {"files": []},
        list_result if list_result is not None else {"files": []},
    ]
    svc.files.return_value.list.return_value = list_exec

    # files().create(...).execute()  — used when folder doesn't exist
    create_exec = MagicMock()
    create_exec.execute.return_value = create_result or {"id": "FOLDER_ID_NEW"}
    svc.files.return_value.create.return_value = create_exec

    # files().get(...).execute()  — used by soft_delete to fetch current parents
    get_exec = MagicMock()
    get_exec.execute.return_value = get_result or {
        "id": "FILE_ID",
        "name": "doc.txt",
        "parents": ["root"],
        "mimeType": "text/plain",
    }
    svc.files.return_value.get.return_value = get_exec

    # files().update(...).execute()  — parent swap for soft_delete
    update_exec = MagicMock()
    update_exec.execute.return_value = update_result or {
        "id": "FILE_ID",
        "name": "doc.txt",
        "parents": ["FOLDER_ID_NEW"],
    }
    svc.files.return_value.update.return_value = update_exec

    return svc


# --- ensure_delete_later_folder ---------------------------------------------

def test_ensure_folder_creates_when_missing():
    svc = _fake_drive(folder_find_result={"files": []})
    fid = drive_common.ensure_delete_later_folder(svc=svc)
    assert fid == "FOLDER_ID_NEW"
    # One list call (search) + one create call.
    svc.files.return_value.create.assert_called_once()
    body = svc.files.return_value.create.call_args.kwargs["body"]
    assert body["name"] == "_delete-later"
    assert body["mimeType"] == drive_common.FOLDER_MIME
    assert body["parents"] == ["root"]


def test_ensure_folder_reuses_when_present():
    svc = _fake_drive(folder_find_result={"files": [{"id": "FOLDER_ID_EXISTING", "name": "_delete-later"}]})
    fid = drive_common.ensure_delete_later_folder(svc=svc)
    assert fid == "FOLDER_ID_EXISTING"
    svc.files.return_value.create.assert_not_called()


def test_ensure_folder_is_cached():
    svc = _fake_drive(folder_find_result={"files": [{"id": "FOLDER_ID_EXISTING"}]})
    drive_common.ensure_delete_later_folder(svc=svc)
    drive_common.ensure_delete_later_folder(svc=svc)
    # Only the first call should hit Drive; the second hits the in-process cache.
    svc.files.return_value.list.assert_called_once()


# --- soft_delete -------------------------------------------------------------

def test_soft_delete_moves_file_to_folder():
    svc = _fake_drive(
        folder_find_result={"files": [{"id": "FOLDER_ID"}]},
        get_result={"id": "F1", "name": "x.doc", "parents": ["PARENT_A"], "mimeType": "m"},
    )
    out = drive_common.soft_delete("F1", svc=svc)
    assert out["ok"] is True
    assert out["already_pending"] is False
    assert out["previous_parents"] == ["PARENT_A"]

    update_kwargs = svc.files.return_value.update.call_args.kwargs
    assert update_kwargs["fileId"] == "F1"
    assert update_kwargs["addParents"] == "FOLDER_ID"
    assert update_kwargs["removeParents"] == "PARENT_A"


def test_soft_delete_is_idempotent_when_already_in_folder():
    svc = _fake_drive(
        folder_find_result={"files": [{"id": "FOLDER_ID"}]},
        get_result={"id": "F1", "name": "x.doc", "parents": ["FOLDER_ID"], "mimeType": "m"},
    )
    out = drive_common.soft_delete("F1", svc=svc)
    assert out["ok"] is True
    assert out["already_pending"] is True
    svc.files.return_value.update.assert_not_called()


def test_soft_delete_handles_multi_parent_file():
    svc = _fake_drive(
        folder_find_result={"files": [{"id": "FOLDER_ID"}]},
        get_result={"id": "F1", "name": "x", "parents": ["P1", "P2"], "mimeType": "m"},
    )
    drive_common.soft_delete("F1", svc=svc)
    kwargs = svc.files.return_value.update.call_args.kwargs
    # Both previous parents removed, target added.
    assert set(kwargs["removeParents"].split(",")) == {"P1", "P2"}


def test_soft_delete_refuses_shared_drive_file():
    """Files with `driveId` set live on a Shared Drive — hard refuse.

    This is the load-bearing safety invariant. No update/delete API call
    should fire regardless of other state.
    """
    svc = _fake_drive(
        folder_find_result={"files": [{"id": "FOLDER_ID"}]},
        get_result={
            "id": "SD_FILE",
            "name": "team-doc",
            "parents": ["SHARED_DRIVE_FOLDER"],
            "mimeType": "application/vnd.google-apps.document",
            "driveId": "SHARED_DRIVE_ID_123",
        },
    )
    out = drive_common.soft_delete("SD_FILE", svc=svc)
    assert out["ok"] is False
    assert out["retryable"] is False
    assert out["drive_id"] == "SHARED_DRIVE_ID_123"
    assert "Shared Drive" in out["error"]
    svc.files.return_value.update.assert_not_called()
    svc.files.return_value.delete.assert_not_called()


# --- list_delete_later -------------------------------------------------------

def test_list_delete_later_returns_files():
    svc = _fake_drive(
        folder_find_result={"files": [{"id": "FOLDER_ID"}]},
        list_result={"files": [{"id": "A", "name": "a.doc"}, {"id": "B", "name": "b.doc"}]},
    )
    out = drive_common.list_delete_later(svc=svc)
    assert out["ok"] is True
    assert out["count"] == 2
    assert out["delete_later_folder_id"] == "FOLDER_ID"
