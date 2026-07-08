"""Tests for Google Tasks tools."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gsuite.tools import tasks_tools


@pytest.fixture
def fake_svc(monkeypatch):
    svc = MagicMock()
    monkeypatch.setattr(tasks_tools, "_svc", lambda: svc)
    return svc


def test_tasklists_list(fake_svc):
    fake_svc.tasklists.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "L1", "title": "My List", "updated": "2026-07-08T00:00:00Z"}]
    }
    out = tasks_tools.tasklists_list()
    assert out["count"] == 1
    assert out["tasklists"][0]["id"] == "L1"


def test_tasks_list_hides_completed_by_default(fake_svc):
    fake_svc.tasks.return_value.list.return_value.execute.return_value = {"items": []}
    tasks_tools.tasks_list()
    kwargs = fake_svc.tasks.return_value.list.call_args.kwargs
    assert kwargs["tasklist"] == "@default"
    assert kwargs["showCompleted"] is False
    assert "showHidden" not in kwargs


def test_tasks_list_show_completed_sets_hidden(fake_svc):
    fake_svc.tasks.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "T1", "title": "done", "status": "completed"}]
    }
    out = tasks_tools.tasks_list(show_completed=True)
    kwargs = fake_svc.tasks.return_value.list.call_args.kwargs
    assert kwargs["showCompleted"] is True
    assert kwargs["showHidden"] is True
    assert out["tasks"][0]["status"] == "completed"


def test_tasks_create_builds_body(fake_svc):
    fake_svc.tasks.return_value.insert.return_value.execute.return_value = {
        "id": "NEW", "title": "Call Cody", "status": "needsAction",
    }
    out = tasks_tools.tasks_create(title="Call Cody", notes="re: invoice")
    assert out["id"] == "NEW"
    kwargs = fake_svc.tasks.return_value.insert.call_args.kwargs
    assert kwargs["tasklist"] == "@default"
    assert kwargs["body"] == {"title": "Call Cody", "notes": "re: invoice"}
    assert "parent" not in kwargs


def test_tasks_create_dateless_omits_due(fake_svc):
    fake_svc.tasks.return_value.insert.return_value.execute.return_value = {"id": "N"}
    tasks_tools.tasks_create(title="dateless")
    body = fake_svc.tasks.return_value.insert.call_args.kwargs["body"]
    assert "due" not in body


def test_tasks_create_passes_parent(fake_svc):
    fake_svc.tasks.return_value.insert.return_value.execute.return_value = {"id": "N"}
    tasks_tools.tasks_create(title="sub", parent="P1")
    assert fake_svc.tasks.return_value.insert.call_args.kwargs["parent"] == "P1"


def test_tasks_update_completed_shortcut(fake_svc):
    fake_svc.tasks.return_value.patch.return_value.execute.return_value = {
        "id": "T", "status": "completed",
    }
    out = tasks_tools.tasks_update(task_id="T", completed=True)
    assert out["status"] == "completed"
    body = fake_svc.tasks.return_value.patch.call_args.kwargs["body"]
    assert body == {"status": "completed"}


def test_tasks_update_reopen_clears_completed(fake_svc):
    fake_svc.tasks.return_value.patch.return_value.execute.return_value = {
        "id": "T", "status": "needsAction",
    }
    tasks_tools.tasks_update(task_id="T", completed=False)
    body = fake_svc.tasks.return_value.patch.call_args.kwargs["body"]
    assert body["status"] == "needsAction"
    assert body["completed"] is None


def test_tasks_update_clear_due(fake_svc):
    fake_svc.tasks.return_value.patch.return_value.execute.return_value = {"id": "T"}
    tasks_tools.tasks_update(task_id="T", due="")
    body = fake_svc.tasks.return_value.patch.call_args.kwargs["body"]
    assert body["due"] is None


def test_tasks_update_rejects_completed_and_status(fake_svc):
    out = tasks_tools.tasks_update(task_id="T", completed=True, status="needsAction")
    assert out["ok"] is False


def test_tasks_update_rejects_empty_patch(fake_svc):
    out = tasks_tools.tasks_update(task_id="T")
    assert out["ok"] is False


def test_tasks_delete(fake_svc):
    fake_svc.tasks.return_value.delete.return_value.execute.return_value = ""
    out = tasks_tools.tasks_delete(task_id="T")
    assert out["deleted"] is True
    kwargs = fake_svc.tasks.return_value.delete.call_args.kwargs
    assert kwargs["tasklist"] == "@default"
    assert kwargs["task"] == "T"
