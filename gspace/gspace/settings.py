"""Feature flags and OAuth scope mapping.

The user controls what the MCP can do via ~/.config/gspace/settings.json.
Each feature maps to the Gmail/Drive/Calendar scopes it needs; the auth layer
asks Google for the union of scopes for enabled features and nothing more.

Disabling a feature in settings.json hides its tools from Claude the next time
the server starts — no code change required. Enabling a feature whose scopes
aren't in the current tokens triggers a "run `gspace auth`" message and
leaves the tool disabled until the user re-consents.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(
    os.environ.get("GSPACE_CONFIG_DIR", Path.home() / ".config" / "gspace")
)
SETTINGS_PATH = CONFIG_DIR / "settings.json"
TOKENS_PATH = CONFIG_DIR / "tokens.json"
OAUTH_CLIENT_PATH = CONFIG_DIR / "oauth-client.json"
BACKUPS_DIR = CONFIG_DIR / "backups"

# Each feature → list of Google OAuth scopes needed to serve its tools.
# Keep keys dotted (domain.action) to mirror the tool namespace.
FEATURE_SCOPES: dict[str, list[str]] = {
    "gmail.read": ["https://www.googleapis.com/auth/gmail.readonly"],
    # Compose+send (drafts AND sending). drafts.create needs gmail.modify, not
    # the narrower gmail.send scope — and modify is already granted on every
    # account, so hosting these here means no re-consent.
    "gmail.send": ["https://www.googleapis.com/auth/gmail.modify"],
    "gmail.filters": ["https://www.googleapis.com/auth/gmail.settings.basic"],
    "gmail.bulk_modify": ["https://www.googleapis.com/auth/gmail.modify"],
    "gmail.classify": ["https://www.googleapis.com/auth/gmail.modify"],
    "drive.read": ["https://www.googleapis.com/auth/drive.readonly"],
    "drive.write": ["https://www.googleapis.com/auth/drive"],
    "docs.read": ["https://www.googleapis.com/auth/documents.readonly"],
    "docs.write": ["https://www.googleapis.com/auth/documents"],
    "sheets.read": ["https://www.googleapis.com/auth/spreadsheets.readonly"],
    "sheets.write": ["https://www.googleapis.com/auth/spreadsheets"],
    "slides.read": ["https://www.googleapis.com/auth/presentations.readonly"],
    "slides.write": ["https://www.googleapis.com/auth/presentations"],
    "calendar.read": ["https://www.googleapis.com/auth/calendar.readonly"],
    "calendar.write": [
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/calendar.events",
    ],
    "tasks": ["https://www.googleapis.com/auth/tasks"],
}

# Map old single-key flags to the new read/write pair. Loaded settings are
# migrated in-memory; the migrated version is written back on next save.
LEGACY_FEATURE_ALIASES: dict[str, list[str]] = {
    "docs": ["docs.read", "docs.write"],
    "sheets": ["sheets.read", "sheets.write"],
    "slides": ["slides.read", "slides.write"],
    "calendar": ["calendar.read", "calendar.write"],
}

DEFAULT_FEATURES: dict[str, bool] = {
    "gmail.read": True,
    "gmail.send": True,
    "gmail.filters": True,
    "gmail.bulk_modify": True,
    "gmail.classify": False,
    "drive.read": False,
    "drive.write": False,
    "docs.read": False,
    "docs.write": False,
    "sheets.read": False,
    "sheets.write": False,
    "slides.read": False,
    "slides.write": False,
    "calendar.read": False,
    "calendar.write": False,
    "tasks": False,
}

DEFAULT_LLM: dict[str, Any] = {
    "model": "claude-haiku-4-5-20251001",
    "classify_max_tokens": 256,
}

# Google scope subsumption: when the superset is granted, the subsets are
# redundant and should not be re-requested. Keys are supersets.
SCOPE_SUBSUMPTION: dict[str, set[str]] = {
    "https://www.googleapis.com/auth/gmail.modify": {
        "https://www.googleapis.com/auth/gmail.readonly",
    },
    "https://www.googleapis.com/auth/drive": {
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/drive.file",
    },
    "https://www.googleapis.com/auth/calendar": {
        "https://www.googleapis.com/auth/calendar.events",
        "https://www.googleapis.com/auth/calendar.readonly",
    },
    "https://www.googleapis.com/auth/documents": {
        "https://www.googleapis.com/auth/documents.readonly",
    },
    "https://www.googleapis.com/auth/spreadsheets": {
        "https://www.googleapis.com/auth/spreadsheets.readonly",
    },
    "https://www.googleapis.com/auth/presentations": {
        "https://www.googleapis.com/auth/presentations.readonly",
    },
}


def _collapse_scopes(scopes: set[str]) -> set[str]:
    """Drop scopes that are covered by a superset already in the set."""
    out = set(scopes)
    for superset, covered in SCOPE_SUBSUMPTION.items():
        if superset in out:
            out -= covered
    return out


@dataclass
class Settings:
    features: dict[str, bool]
    llm: dict[str, Any]

    def enabled_features(self) -> list[str]:
        return sorted(f for f, on in self.features.items() if on)

    def required_scopes(self) -> set[str]:
        out: set[str] = set()
        for f in self.enabled_features():
            out.update(FEATURE_SCOPES.get(f, []))
        return _collapse_scopes(out)

    def to_dict(self) -> dict[str, Any]:
        return {"features": dict(self.features), "llm": dict(self.llm)}


def _ensure_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)


def _migrate_legacy_features(raw: dict[str, bool]) -> dict[str, bool]:
    """Expand legacy `docs`/`sheets`/`slides`/`calendar` flags into read+write pairs.

    The user's on-disk settings predate the read/write split; when we see an
    old key, we fan its value out to both halves and drop the old key. The
    next `save_settings` call persists the migrated shape.
    """
    out = dict(raw)
    for old, new_keys in LEGACY_FEATURE_ALIASES.items():
        if old in out:
            val = bool(out.pop(old))
            for nk in new_keys:
                out.setdefault(nk, val)
    return out


def load_settings() -> Settings:
    _ensure_dirs()
    if not SETTINGS_PATH.exists():
        s = Settings(features=dict(DEFAULT_FEATURES), llm=dict(DEFAULT_LLM))
        save_settings(s)
        return s
    raw = json.loads(SETTINGS_PATH.read_text())
    features = dict(DEFAULT_FEATURES)
    features.update(_migrate_legacy_features(raw.get("features", {})))
    llm = dict(DEFAULT_LLM)
    llm.update(raw.get("llm", {}))
    return Settings(features=features, llm=llm)


def save_settings(settings: Settings) -> None:
    _ensure_dirs()
    SETTINGS_PATH.write_text(json.dumps(settings.to_dict(), indent=2) + "\n")


def set_feature(name: str, enabled: bool) -> Settings:
    if name not in FEATURE_SCOPES:
        raise KeyError(f"unknown feature: {name!r} (known: {sorted(FEATURE_SCOPES)})")
    s = load_settings()
    s.features[name] = enabled
    save_settings(s)
    return s


def scope_gaps(granted: set[str], required: set[str]) -> set[str]:
    """Return scopes required by enabled features but not in the current tokens.

    Accounts for subsumption — if granted contains the modify superset, the
    readonly subset is considered satisfied.
    """
    effective = set(granted)
    for superset, covered in SCOPE_SUBSUMPTION.items():
        if superset in effective:
            effective |= covered
    return required - effective
