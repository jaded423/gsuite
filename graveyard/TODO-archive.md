# gsuite TODO archive

Completed TODO items moved out of `TODO.md` (archive rule: >25 lines). Newest on top.

---

- [x] **Propose machine-contract addendum to Global's Tier-2 convention.** DONE — Global
      bit. `~/.claude/CLAUDE.md` § "Memory Architecture" now carries the rule: *machine-defined
      contracts — a code-defined list (tool rosters, schema cols, pipeline steps, ID sets) has
      ONE home = the code; docs POINT/cite, never re-tabulate.* Staged in the `j:Claude` (global)
      session 2026-07-07, confirmed landed 2026-07-28. Evidence/analogue that motivated it =
      elevatedWeb `sheets_desc.py:51 HEADER` drifted 4/5/6 vs docstring/wiki; counter-example
      done right = `acf-field-keys.json` (wiki points, never copies). gsuite pilots it
      (`gsuite tools` + `EXPECTED_TOOLS`).

- [x] **🗓 Bug: `calendar_create_event` can't create an all-day event.** `added 2026-07-25`.
      **DONE 2026-07-25** — 6/6 live cases created+deleted on gsuite-brown; Google stored
      case 1 as `{"date": "2026-08-03"}` → `{"date": "2026-08-04"}`, a real all-day event.
      Elevated (read-only check): bare `09:00` → `9:00–9:30 America/Chicago`. `_event_times()`
      takes all three shapes, `end` optional, same parsing in `calendar_update_event`.
      23 new tests → 165 repo-wide. Detail: [changelog](../docs/changelog.md) 2026-07-25.
      Per-run consumers (`claude -p`) pick this up automatically; only long-lived sessions
      (open Claude Code / Desktop) hold the stale module until restarted.
      verify: grep -c '"date":' gsuite/tools/calendar_tools.py

- [x] **Attendees without notification should be unreachable.** `added 2026-07-25`.
      **DONE 2026-07-25** — `_resolve_send_updates()` shipped with the all-day fix, same file,
      same restart; live runs echoed `notified=none` correctly for the no-attendee cases.
      Unset → `"all"` with attendees, `"none"` without; explicit wins either way; responses echo
      `notified`. Applies to create *and* the attendee-replacing update.
      **Left alone on purpose:** `calendar_delete_event` still defaults to `"none"` — it can't
      see attendees without a fetch, so a silent cancellation is still reachable. Own item if
      it bites.
      verify: grep -q '_resolve_send_updates' gsuite/tools/calendar_tools.py && echo WIRED

      *(original ask, 2026-07-25)* `send_updates` defaulted to `"none"`, so any caller that
      passed `attendees` but omitted `send_updates="all"` silently created an event nobody was
      told about. In the meeting app that instruction lived only in a **prompt sentence**
      (`meeting/assistant/brain.py:172`) — one model slip = no invites, and the symptom looks
      exactly like a mail-delivery failure (Joshua chased that on 2026-07-25 before we traced it
      to Tasks). Fix: when `attendees` is non-empty and `send_updates` is still the default,
      promote it to `"all"`; adding a guest *is* the intent to invite them. Cheap, no re-consent.

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

- [x] **`/log` the 2026-07-07 session.** DONE 2026-07-08 — paper trail confirmed complete:
      both the 07-07 (Gmail expansion + doc slim-down) and 07-08 (Tasks/Calendar/Drive/labels)
      entries live in `docs/changelog.md`. `/log` also synced the global routing-map count
      (`~/.claude/docs/changelog.md` entry for the 51→63 pointer). No duplicate entry needed.

- [x] **Commit + push gsuite.** DONE 2026-07-08 — snapshot push (whole mcp hub + children).
      Two gsuite commits: `d25806c` (Dax removal on install.sh/setup-org-clients.sh/INSTALL.md,
      the pre-existing WIP) + `6b31b92` (07-07 Gmail expansion + 07-08 Tasks/Calendar/Drive/
      labels + docs). Pushed to `jaded423/gsuite` master. Cross-repo count-sync pointers also
      pushed: `mcp` (`d313498`, folded into its wiki-buildout commit); `~/.claude` edits left
      for the manual global cycle (Tier-0, outside mcp scope).

- [x] Add `sheets_add_sheet` (+ `sheets_rename_sheet`, `sheets_delete_sheet`) tools to the gsuite MCP — create/rename/delete tabs within a spreadsheet. DONE 2026-06-17 — `gsuite/gsuite/tools/sheets_tools.py`, feature `sheets.write` (existing scope, no re-consent). All three go through Sheets `batchUpdate` (addSheet / updateSheetProperties / deleteSheet); rename+delete accept `sheet_id` (gid) OR current `title` via `_resolve_sheet_id` helper. Registry test + 9 new unit tests, 110 tests pass. Original note: only sheets_create (whole spreadsheet) existed; hit while scaffolding the Point4 photo-pool sheet (one tab per pillar).

- [x] Add `gmail_update_draft` + `gmail_delete_draft` tools. DONE 2026-06-12 —
      `gsuite/gsuite/tools/gmail_compose.py`, feature `gmail.send` (existing
      `gmail.modify` scope, no re-consent), registry test updated, 101 tests pass.
      Original note: Gmail API supports
      `drafts.update` / `drafts.delete`; gsuite only exposes `gmail_create_draft`, so
      editing a draft currently requires trash-via-`gmail_batch_modify` (add TRASH
      label) + re-create — clumsy and loses the draft_id. Surfaced 2026-06-12 editing
      a Point4 draft for Cody.
