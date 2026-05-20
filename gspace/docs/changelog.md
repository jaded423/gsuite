# gspace changelog

All notable changes to the gspace in-house MCP server.

---

## 2026-04-17 — Shipped, renamed, retired predecessor

**What changed:**

- **Renamed `mcp-elevated` → `gspace`.** Moved into its own subdir `~/projects/mcp/gspace/`, making the parent `~/projects/mcp/` a multi-MCP workspace. New package name `gspace`, new CLI entry point, new config dir `~/.config/gspace/`. Fresh `.venv`, editable install.
- **Phase 5 tool port shipped.** Added Drive (8), Docs (4), Sheets (4), Slides (4), Calendar (3) — 23 new tools on top of the 14 Gmail tools. Feature flags split into `.read` / `.write` pairs for finer scope control, with in-memory migration of legacy flat-flag settings.
- **Shared Drive support added mid-session.** `drive_search` and `drive_list_folder` now include Shared Drive content (`includeItemsFromAllDrives=true`, `supportsAllDrives=true`, `corpora='allDrives'`). `drive_search` gained optional `drive_id` param for scoping to one Shared Drive. Write tools (`create_folder`, `rename`, `move`, `share`) got `supportsAllDrives=true` so they operate on Shared Drive files.
- **Soft-delete safety hardened.** `drive_soft_delete` now hard-refuses files where `driveId` is set (Shared Drive membership) with a structured error, regardless of caller. The `_delete-later` folder lives in My Drive, so cross-drive moves would fail anyway, but the upfront refusal is unambiguous.
- **New tool `drive_get_metadata`** (drive.read). Resolves a bare file ID to full metadata — id/name/mimeType/parents/driveId/owners/modifiedTime/size/webViewLink. Needed to distinguish Shared-Drive vs My-Drive items and to look up human names for parent folder IDs returned by search.
- **Burn-in then retirement of `mcp-elevated`.** Ran side-by-side for a few hours; smoke tested full lifecycle (docs_create → docs_read → drive_soft_delete → drive_list_delete_later). Removed MCP registration and deleted `~/projects/mcp/mcp_elevated*`, the old `.venv`, `pyproject.toml`, `tests/`, `rules/`, `~/.config/mcp-elevated/`.

**Why:**

- Moving to a subdir unblocks adding more in-house MCPs later without cross-contamination.
- `gspace` is a clearer name (matches `gcloud`/`gsutil`/`gh` convention, unambiguous about Google Workspace scope) and doesn't read as "elevated privileges" to outsiders.
- The user works across personal + Shared Drives; without `corpora='allDrives'` the search was silently missing team-drive content (the Elevated Trading Shared Drive holds ~18 COA PDFs that never appeared in earlier queries).
- The Shared-Drive refusal on soft-delete keeps team content safe by construction — even if a caller passes a team-drive file ID, nothing terminal happens to it.

**Files modified (gspace side):**

- `gspace/settings.py` — added `FEATURE_SCOPES` entries for `docs.read/write`, `sheets.read/write`, `slides.read/write`, `calendar.read/write`; added matching `SCOPE_SUBSUMPTION` so write scopes cover readonly counterparts; added `_migrate_legacy_features()` for transparent upgrade from old flat flags.
- `gspace/tools/drive_common.py` — `_get_file()` now fetches `driveId`; `soft_delete()` refuses Shared Drive files upfront.
- `gspace/tools/drive_tools.py` — added `drive_get_metadata`, Shared Drive flags on all search/list/write calls, `drive_id` param on `drive_search`, `driveId` in returned fields.
- `gspace/tools/docs_tools.py`, `sheets_tools.py`, `slides_tools.py`, `calendar_tools.py` — new modules (4/4/4/3 tools).
- `gspace/tools/__init__.py` — imports all six tool modules so decorators fire at import time.
- `gspace/server.py` — bumped server name to `gspace`, unified error shape with `{ok: false, error, retryable}` on exception paths.
- `pyproject.toml` — package name, script entrypoint, find-packages include.
- `tests/test_drive_common.py`, `test_drive_tools.py`, `test_docs_tools.py`, `test_sheets_tools.py`, `test_slides_tools.py`, `test_calendar_tools.py`, `test_settings_migration.py`, `test_registry.py`, `test_errors.py`, `test_rate_limit.py` — 101 tests total, covering: rule engine idempotency, registry self-registration, structured-error contract, rate-limiter bucket + backoff, settings migration + scope subsumption, every tool's request shape, Shared Drive refusal.

**Technical notes:**

- Tool count 37 → 38 after adding `drive_get_metadata` mid-session. All new tools default OFF until user explicitly enables them in `~/.config/gspace/settings.json` + runs `gspace auth`.
- Rate limiter is thread-safe (`threading.Lock`) because the MCP server offloads each handler to `asyncio.to_thread`, so concurrent tool calls share the bucket.
- The regex guard in `tests/test_errors.py` (`test_no_legacy_error_literals_in_tools`) fails CI if anyone adds a new `{"ok": False, "error": ...}` literal instead of going through `_errors.error()`.
- `drive_soft_delete` live-tested against a file whose parent was `0AN4XBgcsk6EKUk9PVA` (a `0A`-prefixed ID that looks like a Shared Drive root but wasn't — Google did not populate `driveId` on that file, so the refusal correctly didn't trigger). The refusal path is covered by `test_soft_delete_refuses_shared_drive_file` in the unit suite.
- Config at `~/.config/gspace/` was seeded by copying the original `~/.config/mcp-elevated/`, so OAuth tokens carried over without a forced re-auth (the user did re-auth once after enabling the new scoped feature flags).

---
