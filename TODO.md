# gsuite TODO

- [ ] **Remint the OAuth client off Elevated GCP into personal `danger-zone-007`
      project** (memory: gsuite-oauth-client-move). Steps: neutral consent-screen
      name (shared with n8n client — one consent screen per project), new Desktop-type
      OAuth client, replace `oauth-client.json` in all 4 `~/.config/gsuite*` dirs,
      re-auth all 4 accounts, re-add Cody as test user on Danger Zone (his 2026-06-12
      test-user registration is on the ELEVATED project and does NOT carry over).
      ⚠ Timing: do this BEFORE Cody installs gsuite, or coordinate his re-add +
      re-auth after. Agreed 2026-06-12 to do it soon for exactly this reason.

- [x] Add `gmail_update_draft` + `gmail_delete_draft` tools. DONE 2026-06-12 —
      `gsuite/gsuite/tools/gmail_compose.py`, feature `gmail.send` (existing
      `gmail.modify` scope, no re-consent), registry test updated, 101 tests pass.
      Original note: Gmail API supports
      `drafts.update` / `drafts.delete`; gsuite only exposes `gmail_create_draft`, so
      editing a draft currently requires trash-via-`gmail_batch_modify` (add TRASH
      label) + re-create — clumsy and loses the draft_id. Surfaced 2026-06-12 editing
      a Point4 draft for Cody.
