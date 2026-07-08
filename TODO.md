# gsuite TODO

- [ ] **⏸ SHELVED 2026-06-17 — OAuth migration to per-org Internal apps.**
      Full design + resume runbook live in `CLAUDE.md` → "Multi-org OAuth
      architecture" (see the SHELVED banner at its top). Brain:
      `gsuite-oauth-architecture`.

      **Stop-gap in effect (working today):** all 4 accounts share the ONE Elevated
      Desktop client `664420379329-…` in project `ancient-sunspot-471815-g9`, single
      **External app in Testing**. All 4 authed + connected; Joshua has live access
      to every mailbox; Cody uses it by clicking through the "unverified app" warning
      once. Good enough — don't touch until there's appetite for the cutover.

      **Why deferred:** the split is piecewise — each account loses access until its
      own Internal client is built + consent screen flipped Internal + re-authed.
      Not worth trading a fully-working setup for a half-migrated one right now.

      **Target when resumed:** per-org **Internal** OAuth apps (no verification, no
      CASA, no 7-day expiry; Elevated's Internal app auto-covers Cody) + jaded on
      External/Testing. Use `setup-org-clients.sh` (NOT the deprecated
      `remint-oauth.sh`). Branding (JadedViber) + a `danger-zone-007` "tools" Desktop
      client are already staged for the future jaded instance.

      **Kept, NOT shelved:** dir rename `~/.config/gsuite` → `~/.config/gsuite-elevated`
      (agnostic naming; `install.sh`, `setup-org-clients.sh`, `check-oauth.sh`,
      `remint-oauth.sh`, and all 4 MCP registrations already point at it).

- [ ] **Weekly auto-reauth script — GATED on the per-org cutover above; jaded-only.**
      After elevated/dax/point4 move to Internal apps (no token expiry), only the
      consumer `jaded423@gmail.com` instance stays on External/Testing → its
      restricted-scope refresh token still dies ~7 days. Build a Playwright + launchd
      job to re-mint it weekly (e.g. Sun 00:01). Shape: spawn
      `GSUITE_CONFIG_DIR=~/.config/gsuite-jaded gsuite auth` → it prints the
      `localhost:PORT` OAuth URL + blocks on callback → Playwright drives the click
      → token written. Gotchas: (1) Google blocks headless/automation OAuth — use
      `launch_persistent_context` with a real Chrome profile already logged into
      jaded (cookies present → only an "Allow" click, no password/2FA); headed, not
      headless. (2) Mac asleep at fire-time → cron skips; use launchd
      `StartCalendarInterval` (+ `pmset repeat wake` if needed) since tokens live in
      Mac `~/.config/gsuite-jaded`. (3) Match account by visible email + button text
      `Allow`/`Continue`, not brittle CSS (Google rev's the DOM). Land as
      `gsuite/weekly-reauth.py` + a `.plist`; one-time manual run to seed the profile
      login. Cost note (2026-06-23): making jaded an org to skip this = ~$84/yr
      Workspace + mailbox migration — not worth it for one account; the script is the
      cheap holdout fix. Don't build until the cutover lands (no point scripting 4
      accounts when 3 get fixed permanently).

- [ ] **Bug: `check-oauth.sh` has a bash shebang but breaks under `sh`** (`line 17:
      elevated: unbound variable` — associative arrays). Either it's only ever run as
      `./check-oauth.sh`/`bash check-oauth.sh` (fine, low prio) or add a `sh`-safe
      guard. Same risk in `setup-org-clients.sh` (also uses `declare -A`).

- [ ] **`/log` the 2026-07-07 session** once satisfied — Gmail email expansion
      (attachments, HTML, threading, `gmail_get_attachment`/`gmail_send_draft`/
      `gmail_get_thread`, +3 tools → 51) + the Tier-2 doc slim-down (CLAUDE.md 558→~250,
      history extracted to `docs/design-and-history.md`, `gsuite tools` roster command).
      Routes to gsuite. Changelog entry already written; `/log` for the paper trail.

- [ ] **Commit + push gsuite.** Uncommitted across two sessions:
      • 2026-07-07: `tools/gmail_compose.py`, `gmail_messages.py`, `cli.py`,
        `tests/test_gmail_messages.py` (new), `tests/test_registry.py`, `CLAUDE.md`,
        `docs/{index,changelog,design-and-history}.md`.
      • 2026-07-08 (Tasks + Calendar/Drive/labels): `tools/tasks_tools.py` (new),
        `tools/gmail_labels.py` (new), `tools/calendar_tools.py`, `tools/drive_tools.py`,
        `tools/__init__.py`, `tests/test_tasks_tools.py` + `test_gmail_labels.py` (new),
        `tests/test_{calendar,drive}_tools.py`, `tests/test_registry.py`, `TODO.md`,
        `graveyard/TODO-archive.md` (new). Also touched OUTSIDE gsuite: `~/.claude/CLAUDE.md`,
        `~/projects/mcp/wiki/components/gsuite.md` (tool-count 51→63 sync).
      ⚠ Working tree ALSO has pre-existing WIP from another session (`install.sh`,
      `setup-org-clients.sh`) — do NOT clobber; commit selectively.

- [ ] **Contacts / People resolve tool** (`people_search`, name→address — e.g. "Cody"
      → cody@elevatedtrading.com). Draft-to-name is constant friction. **Cost: NEW People
      API scope = OAuth re-consent on all 3 instances.** Decide if worth the re-auth.

- [x] **Calendar CRUD + Drive read + Gmail labels.** DONE 2026-07-08 — closed the biggest
      no-re-consent gaps found auditing the roster:
      • Calendar (`calendar_tools.py`): `calendar_get_event`, `calendar_list_calendars`
        (read), `calendar_delete_event`, `calendar_respond_to_event` (RSVP — patches only
        self attendee). Was 3 verbs, now 7 — full CRUD.
      • Drive (`drive_tools.py`): `drive_read_file` — reads any file's content (native Docs/
        Sheets export to text/CSV; PDF/txt/img downloaded raw → utf-8 or base64, `max_bytes`
        truncation). Drive was write-only for non-native files.
      • Gmail (`gmail_labels.py`, new module): `gmail_list_labels` (read; id↔name map for
        batch_modify) + `gmail_create_label` (bulk_modify scope). 
      All under existing scopes, no re-consent. +8 tools → **63 total / 16 flags**. 13 new
      tests, 142 pass. Live-verified list_calendars + list_labels on elevated.

- [ ] **`gmail_get_thread` follow-ons** (optional): whole-thread attachment index;
      mark-read / archive / star verbs — reachable NOW via `gmail_batch_modify` + system
      label IDs (UNREAD / INBOX / STARRED), and `gmail_list_labels` (added 2026-07-08) makes
      those IDs discoverable. Only add dedicated verbs if the batch_modify path proves clumsy.

- [ ] **Propose machine-contract addendum to Global's Tier-2 convention.** Staged in the
      `j:Claude` (global) session 2026-07-07: *machine-defined lists (tool rosters, output
      schemas, pipeline steps, field maps, ID sets) have ONE home = code; docs cite a count
      + POINT, never re-tabulate; generate or test-guard drift.* Evidence/analogue =
      elevatedWeb `sheets_desc.py:51 HEADER` already drifted 4/5/6 vs docstring/wiki;
      counter-example done right = `acf-field-keys.json` (wiki points, never copies).
      gsuite pilots it (`gsuite tools` + `EXPECTED_TOOLS`). Follow up if Global bites.

> Older completed items archived → [graveyard/TODO-archive.md](graveyard/TODO-archive.md)
> (`gmail_update_draft`/`delete_draft` 2026-06-12, `sheets_add_sheet` et al. 2026-06-17).

- [x] **Build Google Tasks tools.** DONE 2026-07-08 — `gsuite/gsuite/tools/tasks_tools.py`,
      5 tools under the existing `tasks` feature (no re-consent): `tasklists_list`, `tasks_list`
      (hides completed by default), `tasks_create` (dateless-friendly, `parent` for subtasks),
      `tasks_update` (title/notes/due + `completed` shortcut / `status`; reopening clears the
      completion stamp; `due=''` clears date), `tasks_delete`. Registered in `tools/__init__.py`,
      added to `EXPECTED_TOOLS`, 12 new unit tests + registry, 129 pass. `tasks` already enabled
      + scope granted (`missing_scopes: []`) on all 3 instances. Live smoke test (create→complete
      →delete) passed against elevated. **Driver:** trans/plaud meeting→action-items pipeline
      routes dateless items → Tasks (render in Cody's Calendar sidebar). [src:
      `~/projects/trans/docs/meeting-to-tasks-pipeline.md`]
