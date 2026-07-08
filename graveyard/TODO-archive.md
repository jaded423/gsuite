# gsuite TODO archive

Completed TODO items moved out of `TODO.md` (archive rule: >25 lines). Newest on top.

---

- [x] Add `sheets_add_sheet` (+ `sheets_rename_sheet`, `sheets_delete_sheet`) tools to the gsuite MCP — create/rename/delete tabs within a spreadsheet. DONE 2026-06-17 — `gsuite/gsuite/tools/sheets_tools.py`, feature `sheets.write` (existing scope, no re-consent). All three go through Sheets `batchUpdate` (addSheet / updateSheetProperties / deleteSheet); rename+delete accept `sheet_id` (gid) OR current `title` via `_resolve_sheet_id` helper. Registry test + 9 new unit tests, 110 tests pass. Original note: only sheets_create (whole spreadsheet) existed; hit while scaffolding the Point4 photo-pool sheet (one tab per pillar).

- [x] Add `gmail_update_draft` + `gmail_delete_draft` tools. DONE 2026-06-12 —
      `gsuite/gsuite/tools/gmail_compose.py`, feature `gmail.send` (existing
      `gmail.modify` scope, no re-consent), registry test updated, 101 tests pass.
      Original note: Gmail API supports
      `drafts.update` / `drafts.delete`; gsuite only exposes `gmail_create_draft`, so
      editing a draft currently requires trash-via-`gmail_batch_modify` (add TRASH
      label) + re-create — clumsy and loses the draft_id. Surfaced 2026-06-12 editing
      a Point4 draft for Cody.
