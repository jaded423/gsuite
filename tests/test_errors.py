"""Tests for the structured error contract.

Every validation error returned by a tool handler must carry `ok`, `error`,
and `retryable` keys. The test drives the handlers with arguments that trip
their validation guards — no real Google API calls are needed.
"""

from __future__ import annotations

import inspect
import re

import pytest

from gsuite.tools import _errors
from gsuite.tools import gmail_bulk, gmail_classify, gmail_filters, gmail_rules


def _assert_structured(err: dict) -> None:
    assert err.get("ok") is False, err
    assert isinstance(err.get("error"), str) and err["error"], err
    assert isinstance(err.get("retryable"), bool), err


# --- helper ------------------------------------------------------------------

def test_error_helper_shape():
    e = _errors.error("boom", filter_id="abc")
    assert e == {"ok": False, "error": "boom", "retryable": False, "filter_id": "abc"}


def test_error_helper_retryable_flag():
    e = _errors.error("transient", retryable=True)
    assert e["retryable"] is True


# --- validation paths (no network) ------------------------------------------

def test_delete_filter_requires_confirm():
    _assert_structured(gmail_filters.delete_filter("FILTER_ID", confirm=False))


def test_replace_filter_requires_confirm():
    _assert_structured(
        gmail_filters.replace_filter("FILTER_ID", {"from": "a@b"}, {}, confirm=False)
    )


def test_restore_filters_missing_file(tmp_path):
    _assert_structured(gmail_filters.restore_filters(str(tmp_path / "nope.json")))


def test_apply_rules_missing_file(tmp_path):
    _assert_structured(gmail_rules.apply_rules(str(tmp_path / "nope.yaml")))


def test_batch_modify_rejects_empty_label_lists():
    _assert_structured(gmail_bulk.batch_modify("to:a@b.com"))


def test_classify_message_rejects_empty_categories():
    _assert_structured(gmail_classify.classify_message("MSG_ID", []))


# --- no stray `{"ok": False, "error": ...}` literals left in tools ----------

def test_no_legacy_error_literals_in_tools():
    """Every tool-level error must route through `_errors.error`.

    We grep the tool sources for the old `{"ok": False, "error":` pattern —
    any match means a handler is returning an error dict without going
    through the helper, so it'll be missing `retryable`.
    """
    pattern = re.compile(r'\{"ok":\s*False,\s*"error":')
    modules = [gmail_bulk, gmail_classify, gmail_filters, gmail_rules]
    offenders = []
    for mod in modules:
        src = inspect.getsource(mod)
        if pattern.search(src):
            offenders.append(mod.__name__)
    assert offenders == [], (
        f"modules with legacy error literals: {offenders} — use _errors.error()"
    )
