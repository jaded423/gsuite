---
type: log
title: gsuite changelog
tags: [gsuite, changelog, history, log]
related: [index]
---

# gsuite changelog

All notable changes to the gsuite in-house MCP server.

---

## 2026-09-09 — INSTALL.md: "see everything, ask before every change, never send" profile

**What changed:**
- INSTALL.md rewritten around a default access profile for a new user (Cody's install):
  **every feature enabled** (full read/write scopes granted once), with Claude Code's
  `~/.claude/settings.json` as the gate — the 21 read-only tools auto-allowed, every
  write tool left unlisted so it **prompts per call**, and `gmail_send_message` /
  `gmail_send_draft` hard-denied. Plus a `~/.claude/CLAUDE.md` house-rules block, a
  three-check verify (read silent / draft prompts / send refused), and a trust ladder
  where each rung is one line moved to `allow` — no re-auth with Google ever.
- Fixed the stale install command: `pip install -e ./gsuite` → `pip install -e .`
  (the package moved to the repo root 2026-06-15; the old line would have failed).
- Step 3 names which client an @elevatedtrading.com user gets (the Elevated Internal
  app — no test-user step, no "unverified" screen). Claude Desktop marked "not for this
  profile" (no deny list there).

**Why:**
- Joshua's call: Cody gets the full toolset (Sheets/Drive writes included) but gated
  until he's comfortable. Gating in Claude Code instead of feature flags means levelling
  up is a settings edit, not a flag+re-consent dance. `gmail.send` is one flag for
  drafts AND sending (drafts need `gmail.modify`; Google has no draft-only scope), so
  the deny list is the only place "never send" can live. The doc warns that the consent
  screen shows full read/write for everything and says where the real gate is.
- The first draft of this rewrite (same day) used read-only scopes + flag-level locks;
  superseded within the hour by the prompt-gated design above.

**Outcome (same day):** Cody's Claude ran the guide unattended; Joshua supplied only the
Elevated Internal client file. Working in Claude Code AND Claude Desktop, verified with an
inbox-triage question and a LiveRef "total if we sold all Current Inventory" Sheets read.
Desktop was registered despite the guide's caveat — on Desktop only the house rules stand
between Claude and the send tool. Brain: `cody-gsuite-install`.

**Cynthia (same day, parallel session):** her 2026-08-31 install had been gmail-only (default
flags). Non-gmail read features enabled + re-authed. The re-auth exposed a real gotcha —
`gsuite auth` blocks on the browser flow and Claude Code's shell tool times out at 2 min,
killing it mid-consent — now a § 5 note: the person runs it with the `!` prefix, Claude stops
after the flags. She is on read-all + Gmail defaults (send on, no Claude Code gate); whether
she gets Cody's § 7/§ 8 gate is an open TODO. Brain: `cynthia-gsuite-state`.

**Files modified:** `INSTALL.md`, `docs/changelog.md`, `TODO.md`

---

## 2026-07-27 — Classifier key file moves to the shared key store

**What changed:**
- `gmail_classify.py`'s `KEY_FILE` is now **`~/.secrets/anthropic_api_key`** (dir 700, file 600),
  was `~/.anthropic_api_key` in the home root.

**Why:**
- Part of the global `ANTHROPIC_API_KEY` rotation + key-store move (T0 changelog 2026-07-27):
  one key, one location shared with `scripts/bin/gitBackup.sh` and point4pi, so rotating is a
  single file edit.

**Files modified:**
- `gsuite/tools/gmail_classify.py:48` — `KEY_FILE` path

**Technical notes:**
- Resolution order is unchanged — `ANTHROPIC_API_KEY` env first, then the file — and the existing
  docstring rationale still holds verbatim: the key is deliberately not exported globally, same as
  the Google OAuth tokens living in a file under `~/.config`. Only the path moved.
- The classify tools are the only gsuite code that needs an Anthropic key; every other tool is
  unaffected by a rotation.
- Verified the new path resolves and matches the store's fingerprint.

---

## 2026-07-25 — Calendar learns dates *and* times; attendees notified by default

**What changed** (`tools/calendar_tools.py`, no new tools, no re-consent):

- **All-day events work.** The body hardcoded `{"dateTime": …}`, so a date-only value 400'd.
  `start`/`end` now accept three shapes and pick the representation to match:
  `2026-07-28` → all-day `{"date": …}` · `2026-07-28T09:00` → timed, stamped with the
  calendar's own timezone · `2026-07-28T09:00:00-05:00` (or `…Z`) → passed through.
  No more improvised midnight→midnight blocks with a hardcoded `America/Chicago`.
- **`end` is now optional.** All-day defaults to one day (Google's end is exclusive, so
  `start`+1); timed defaults to `duration_minutes`, default 30. An all-day `end` on or before
  the start is read as "this one day" rather than 400'ing.
- **New `timezone` param** (IANA). Only consulted for timed events; when omitted, the
  calendar's own timezone is read once and cached per process — a guess is never used.
- **Attendees are notified by default.** `send_updates` defaulted to `"none"`, so any caller
  that passed `attendees` and forgot it created an event nobody was told about — in the meeting
  app that instruction lived only in a prompt sentence, one model slip from silence. Unset now
  resolves to `"all"` when attendees are present, `"none"` when they aren't; passing it
  explicitly still wins either way. Responses echo the choice as `notified`.
- **`calendar_update_event` got the same parsing**, plus: patching one side of the pair reads
  the event back (Calendar validates the pair, not the field you sent), moving only `start`
  keeps the existing length, and flipping all-day ↔ timed nulls the stale key so the merge
  doesn't leave both `date` and `dateTime` set.
- **`_event_to_summary`** now reports `all_day` and `time_zone`.

Bad input is rejected before the API call with a message that names the fix (mixed
date/datetime shapes, end ≤ start, unparseable strings). +23 tests (34 in the calendar file,
**165 repo-wide**).

**Why:** both were blocking the meeting app's switch to event-by-default for action items —
Tasks has no attendee field, so every dated deliverable that became a task lost its notify
path (proved 2026-07-24: 3 tasks created, `Only me`, nobody told). Unblocks the 9:00am
time-dropdown work on the meeting side.

**Live-verified 2026-07-25** on gsuite-brown: 6/6 cases created + deleted, Google stored the
all-day case as `{"date": "2026-08-03"}` → `{"date": "2026-08-04"}` (a real all-day event, not a
timed block). Read-only check on gsuite-elevated: `_calendar_timezone("primary")` →
`America/Chicago`, so a bare `2026-08-06T09:00` builds `9:00–9:30 America/Chicago` — the meeting
app can send a wall-clock time and know nothing about zones.

**Rollout:** anything spawning a fresh server per run (`claude -p`, so the meeting app) gets
this immediately. Long-lived sessions — an open Claude Code session, Claude Desktop — keep
serving the old schema until restarted.

---

## 2026-07-08 — Google Tasks + Calendar CRUD + Drive read + Gmail labels (+13 tools → 63)

**What changed:**
- **New `tools/tasks_tools.py`** — the scaffolded `tasks` feature finally has tools:
  `tasklists_list`, `tasks_list` (hides completed by default), `tasks_create` (dateless-friendly,
  `parent` for subtasks), `tasks_update` (title/notes/due + `completed` shortcut / explicit
  `status`; reopening clears the completion stamp; `due=''` clears the date), `tasks_delete`.
  Feature + `auth/tasks` scope were pre-staged; already enabled + granted on all 3 instances
  (`missing_scopes: []`) → no re-consent.
- **Calendar filled out** (`tools/calendar_tools.py`, 3 → 7 verbs): `calendar_get_event`,
  `calendar_list_calendars` (read); `calendar_delete_event`, `calendar_respond_to_event` (RSVP,
  patches only the self attendee). Existing `calendar.read`/`.write` scopes.
- **Drive read** (`tools/drive_tools.py`): `drive_read_file` — Google-native Docs/Sheets/Slides
  export to text/CSV; other files (PDF, txt, img) downloaded raw; utf-8 in `content` or base64
  with `encoding='base64'`; `max_bytes` truncation. Closes Drive being write-only for non-native
  files. `drive.read` scope.
- **Gmail labels** (`tools/gmail_labels.py`, NEW): `gmail_list_labels` (read; surfaces the id↔name
  map that `gmail_batch_modify`/`gmail_move_label` need) + `gmail_create_label` (`gmail.bulk_modify`
  scope, clean 409-on-duplicate error).

**Why:** driver was the trans/plaud meeting→action-items pipeline (dateless items → Google Tasks →
Cody's Calendar sidebar). While in the file, audited the whole roster and closed the other
no-re-consent gaps found: Calendar was half-built (couldn't even delete an event), Drive couldn't
read file bytes, Gmail had no way to look up a label id.

**Files modified:** `tools/tasks_tools.py` (new), `tools/gmail_labels.py` (new),
`tools/calendar_tools.py`, `tools/drive_tools.py`, `tools/__init__.py`, `tests/` (+3 new test
files, calendar/drive/registry updated). All under existing scopes — **no re-auth**. 142 tests pass.
Restart each MCP instance to load the new tools.

---

## 2026-07-07 — Tier-2 doc slim-down + machine-contract tool roster

**What changed:**
- **Slimmed `CLAUDE.md` 558 → 247 lines.** Kept the live-operational content (feature-flag/
  scope mechanics, multi-org OAuth model + per-org runbook + gotchas). Extracted the frozen
  design proposal + dated phase build-log to a new **`docs/design-and-history.md`** (`type: log`).
  The Gmail-filter-engine gotchas moved with it but are flagged *still authoritative*.
- **New `docs/design-and-history.md`** — the archived "why"; dated tool counts (14, 37) kept as
  point-in-time snapshots, not current.
- **New `gsuite tools [--json]` CLI subcommand** (`cli.py`) — prints the live tool roster grouped
  by feature, straight from the registry. This is the roster source of truth: no hand-maintained
  `TOOLS.md`, `docs/index.md` cites the count + points at the command, `EXPECTED_TOOLS` guards drift.
- Fixed stale `gspace` → `gsuite` in kept CLAUDE.md operational text + the changelog H1.
- `docs/index.md` updated: history-page row, roster-command note, current-state framing.

**Why:** gsuite is the **pilot Tier-2 repo** for the wiki/brain memory architecture. Global's
light-touch pass (frontmatter + index) deliberately left the 558-line proposal-as-CLAUDE.md as a
separate `/sum` job; this is that pass. The roster pattern (code-defined lists have ONE home = code;
docs point, never re-tabulate; a test guards drift) generalized and was kicked up to global's Tier-2
convention (analogue: elevatedWeb `sheets_desc.py` HEADER already drifted 4/5/6 vs its prose).

**Files modified:**
- `CLAUDE.md` — slimmed to current-state + pointers.
- `docs/design-and-history.md` — NEW, extracted proposal + build-log.
- `gsuite/cli.py` — `tools` subcommand.
- `docs/index.md` — roster note + history row + conventions update.

---

## 2026-07-07 — Gmail attachments, HTML, threading, thread-read, send-draft (+3 tools → 51)

**What changed** (`tools/gmail_compose.py`, `tools/gmail_messages.py`):
- **New `gmail_get_attachment`** (`gmail.read`) — download an attachment by
  `message_id`+`attachment_id` to a local `save_path`; optional `drive_folder_id`
  also uploads a copy to Drive.
- **New `gmail_get_thread`** (`gmail.read`) — read a whole conversation in one call
  (`{thread_id, count, messages}`), compact per-message summaries; `include_body`
  opt-in, `max_messages` cap. Far cheaper than N `gmail_read_message` calls.
- **New `gmail_send_draft`** (`gmail.send`) — send an existing draft by `draft_id`
  (closes the create/update/delete/**send** gap).
- **`gmail_read_message`** now returns an `attachments` array (`filename`,
  `mimeType`, `size`, `attachmentId`) when a message has any — feeds
  `gmail_get_attachment`.
- **`gmail_send_message` / `gmail_create_draft` / `gmail_update_draft`** gained
  `body_type=html`, `attachments` (local paths) + `drive_file_ids` (Drive
  download-then-attach via `MIMEMultipart`/`MIMEBase`), and reply threading
  (`thread_id` + `in_reply_to`/`references` → `In-Reply-To`/`References` headers).
  `_build_raw` rewritten from single-part `MIMEText` to conditional multipart.

**Why:** email portion couldn't attach/receive files, send HTML, or thread
replies. All common real-mail operations.

**No scope change** — `gmail.send` already rides `gmail.modify`, which covers
attachment upload/download and threaded send. No OAuth re-consent. Tool total
48 → 51 across 15 feature flags. New tests: `tests/test_gmail_messages.py`;
`EXPECTED_TOOLS` in `tests/test_registry.py` updated for the 3 new tools.

---

## 2026-07-06 — Detach gsuite-dax instance (Dax Distro dissolved)

**What changed:**
- Removed the `gsuite-dax` user-scope MCP instance (`claude mcp remove gsuite-dax -s user`).
  3 instances remain: `gsuite-elevated`, `gsuite-jaded`, `gsuite-point4`.
- De-looped `dax` so it can't be re-registered: dropped `dax:gsuite-dax` from the `for pair`
  loop in `install.sh`, the `[dax]` entry from `DIR_FOR` + the accounts list in
  `setup-org-clients.sh`, and `dax` from the weekly re-auth loop in `CLAUDE.md` (with a note
  pointing at the teardown bundle). Also trimmed dax from the header comments.
- Config dir `~/.config/gsuite-dax/` (dead `oauth-client.json` + `tokens.json`) moved to
  `~/projects/graveyard/dax-teardown-2026-07/config-gsuite-dax/`.

**Why:**
- Dax Distro dissolved; the Dax Workspace account is gone, and a stale token made the
  instance a recurring re-auth annoyance. Detaching removes it cleanly.

**Note:** gsuite-dax never had a Dax-specific GCP client — all four instances shared the one
Elevated Desktop client `664420379329-…` in project `ancient-sunspot-471815-g9`, so there was
no Dax-side GCP cleanup. The other 3 instances are unaffected (verified `claude mcp list`).

**Files modified:**
- `install.sh` — removed `dax:gsuite-dax` from the registration loop + header comment
- `setup-org-clients.sh` — removed `[dax]` DIR_FOR entry, accounts list, header comment
- `CLAUDE.md` — re-auth loop 4→3 accounts + teardown note

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
