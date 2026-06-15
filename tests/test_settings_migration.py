"""Tests for the docs/sheets/slides/calendar flag split + migration.

The previous schema had flat `docs`, `sheets`, `slides`, `calendar` booleans.
Phase 5 splits each into `.read` / `.write` so scope control is finer. Existing
on-disk settings must migrate silently.
"""

from __future__ import annotations

import json

import pytest

from gsuite import settings as s


def _write_settings(tmp_path, data):
    cfg = tmp_path / "gsuite"
    cfg.mkdir()
    (cfg / "settings.json").write_text(json.dumps(data))
    return cfg


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    cfg = tmp_path / "gsuite"
    cfg.mkdir()
    monkeypatch.setattr(s, "CONFIG_DIR", cfg)
    monkeypatch.setattr(s, "SETTINGS_PATH", cfg / "settings.json")
    monkeypatch.setattr(s, "TOKENS_PATH", cfg / "tokens.json")
    monkeypatch.setattr(s, "OAUTH_CLIENT_PATH", cfg / "oauth-client.json")
    monkeypatch.setattr(s, "BACKUPS_DIR", cfg / "backups")
    yield cfg


def test_migrate_legacy_docs_flag_expands_to_read_and_write():
    raw = {"docs": True}
    migrated = s._migrate_legacy_features(raw)
    assert migrated == {"docs.read": True, "docs.write": True}


def test_migrate_legacy_flag_preserves_false_value():
    raw = {"sheets": False}
    migrated = s._migrate_legacy_features(raw)
    assert migrated == {"sheets.read": False, "sheets.write": False}


def test_migration_does_not_override_explicit_new_keys():
    raw = {"docs": True, "docs.read": False}
    migrated = s._migrate_legacy_features(raw)
    # Explicit new key wins — user may have downgraded just one half.
    assert migrated["docs.read"] is False
    assert migrated["docs.write"] is True


def test_load_settings_migrates_on_disk_file(isolated_config):
    (isolated_config / "settings.json").write_text(
        json.dumps({"features": {"calendar": True, "gmail.read": True}})
    )
    loaded = s.load_settings()
    assert loaded.features["calendar.read"] is True
    assert loaded.features["calendar.write"] is True
    assert "calendar" not in loaded.features  # legacy key removed


# --- scope subsumption -------------------------------------------------------

def test_write_scope_subsumes_read_scope_for_docs():
    granted = {"https://www.googleapis.com/auth/documents"}
    required = {
        "https://www.googleapis.com/auth/documents.readonly",
        "https://www.googleapis.com/auth/documents",
    }
    assert s.scope_gaps(granted, required) == set()


@pytest.mark.parametrize(
    "api",
    ["documents", "spreadsheets", "presentations"],
)
def test_write_scope_subsumes_read_scope_across_apis(api):
    base = f"https://www.googleapis.com/auth/{api}"
    granted = {base}
    required = {f"{base}.readonly"}
    assert s.scope_gaps(granted, required) == set()
