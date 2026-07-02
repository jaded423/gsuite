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

- [x] Add `gmail_update_draft` + `gmail_delete_draft` tools. DONE 2026-06-12 —
      `gsuite/gsuite/tools/gmail_compose.py`, feature `gmail.send` (existing
      `gmail.modify` scope, no re-consent), registry test updated, 101 tests pass.
      Original note: Gmail API supports
      `drafts.update` / `drafts.delete`; gsuite only exposes `gmail_create_draft`, so
      editing a draft currently requires trash-via-`gmail_batch_modify` (add TRASH
      label) + re-create — clumsy and loses the draft_id. Surfaced 2026-06-12 editing
      a Point4 draft for Cody.
- [x] Add `sheets_add_sheet` (+ `sheets_rename_sheet`, `sheets_delete_sheet`) tools to the gsuite MCP — create/rename/delete tabs within a spreadsheet. DONE 2026-06-17 — `gsuite/gsuite/tools/sheets_tools.py`, feature `sheets.write` (existing scope, no re-consent). All three go through Sheets `batchUpdate` (addSheet / updateSheetProperties / deleteSheet); rename+delete accept `sheet_id` (gid) OR current `title` via `_resolve_sheet_id` helper. Registry test + 9 new unit tests, 110 tests pass. Original note: only sheets_create (whole spreadsheet) existed; hit while scaffolding the Point4 photo-pool sheet (one tab per pillar).
