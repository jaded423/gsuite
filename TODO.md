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
