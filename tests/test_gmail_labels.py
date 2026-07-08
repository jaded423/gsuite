"""Tests for Gmail label tools."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gsuite.tools import gmail_labels


@pytest.fixture
def fake_gmail(monkeypatch):
    svc = MagicMock()
    monkeypatch.setattr(gmail_labels, "_gmail", lambda: svc)
    return svc


def test_list_labels_sorts_user_first(fake_gmail):
    fake_gmail.users.return_value.labels.return_value.list.return_value.execute.return_value = {
        "labels": [
            {"id": "INBOX", "name": "INBOX", "type": "system"},
            {"id": "L1", "name": "Zebra", "type": "user"},
            {"id": "L2", "name": "apple", "type": "user"},
        ]
    }
    out = gmail_labels.gmail_list_labels()
    assert out["count"] == 3
    # user labels first, then case-insensitive by name
    names = [l["name"] for l in out["labels"]]
    assert names == ["apple", "Zebra", "INBOX"]


def test_create_label_builds_body(fake_gmail):
    fake_gmail.users.return_value.labels.return_value.create.return_value.execute.return_value = {
        "id": "NEW", "name": "Clients/Acme", "type": "user",
    }
    out = gmail_labels.gmail_create_label(name="Clients/Acme")
    assert out["id"] == "NEW"
    body = fake_gmail.users.return_value.labels.return_value.create.call_args.kwargs["body"]
    assert body["name"] == "Clients/Acme"
    assert body["labelListVisibility"] == "labelShow"


def test_create_label_duplicate_is_clean_error(fake_gmail):
    fake_gmail.users.return_value.labels.return_value.create.return_value.execute.side_effect = (
        Exception("HttpError 409 already exists")
    )
    out = gmail_labels.gmail_create_label(name="Dupe")
    assert out["ok"] is False
    assert "already exists" in out["error"]
