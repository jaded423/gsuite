# gsuite TODO

- [x] **Cynthia install follow-up + streamline INSTALL.md before Cody's install.** (added 2026-08-31; done 2026-09-09)
      Evidence: INSTALL.md rewritten (profile §0, explicit flags §4, gate §7/§8, 3-check
      verify, trust ladder, stale pip path fixed, `! gsuite auth` timeout note in §5).
      Cody installed from it unattended same day (CLI + Desktop, verified). Cynthia's
      non-gmail read features enabled + re-authed same day (parallel session; the re-auth
      surfaced the shell-timeout gotcha that became the §5 note).
- [x] **Decide: put Cynthia on Cody's gate?** (added 2026-09-09; decided 2026-09-09: NO)
      Deliberate difference, not drift: Cynthia is less skeptical and holds less sensitive
      data, so she had no draft-only stipulation before install. Cody's gate stays Cody's.

- [x] 2026-10-06 — fixed the same day with option (a), minus the settings field: `gsuite auth --expect <email>` preselects the account (`login_hint`) and refuses to save a login from any other (or one it cannot identify); `setup-org-clients.sh` passes it from an `EMAIL_FOR` roster and names the account in its prompt; new `add-account.sh <name> <email> <feature>…` always passes it. Tests: `tests/test_auth_expect.py` (4), suite 180 passed. Not done: option (c), `gsuite status` printing the account. Was: **An account's login can land in the wrong account's folder, and nothing notices.** (added 2026-10-06)
      Happened 2026-10-06: `setup-org-clients.sh jaded=… brown=…` asks in hash order
      (brown first, then jaded), the browser chooser does not say which folder it is
      for, and `gsuite auth` stores whatever account was picked. Result: `gsuite-jaded`
      read brown's mailbox and `gsuite-brown` read jaded423's until the two
      `tokens.json` files were swapped. The order half is fixed (2026-10-06: the script
      now keeps an `ORDER` list and asks in the order typed); what is left is that
      nothing checks who signed in. Options (Claude's, not yet picked):
      (a) each config dir names its account (`"account"` in `settings.json`);
      `gsuite auth` passes it as `login_hint` so the chooser preselects it, then
      refuses to save a login whose Gmail profile address differs; (b) guard only in
      `setup-org-clients.sh`: after each auth, compare the profile address with an
      expected-address roster and roll back on mismatch; (c) `gsuite status` prints
      the account address, so `check-oauth.sh` shows a crossed pair at a glance.
      (a) removes the failure; (c) is the cheap visibility half.

- [ ] **Move the two Gmail instances (jaded, brown) to a PUBLISHED External app Joshua owns — ends the weekly reauth.** (added 2026-10-05)
      resume (2026-10-06 ~11:30 CDT): Joshua chose to flip `mcps` itself instead of a
      second project (his call, accepting that j@ rides the untested rule too; it can
      be switched back with "Make internal"). DONE in the console as j@: Branding got
      home/privacy/terms links (`jadedviber.com/app|privacy|terms`) + authorized domain
      `jadedviber.com`, no logo (a logo forces verification); Audience is now
      **External / In production**, 0 of 100 users. j@ still refreshes on the Pocket,
      multi-verse and ubuntu (forced refresh on each, after the flip). Checked the same
      day: none of j@ / jaded423 / brown can open `ancient-sunspot-471815-g9`, so it is
      Elevated's. brown confirmed on the same old client as jaded (`check-oauth.sh`
      now lists it).
      DONE the same day (~12:30 CDT): Joshua ran
      `./setup-org-clients.sh jaded=… brown=…` with the `mcps` client file (one
      Desktop client for all three accounts); the two logins landed crossed (item
      above) and he swapped the `tokens.json` files. Verified after the swap: the
      verify line returns 0, `gsuite-jaded` reads jaded423's mailbox and
      `gsuite-brown` reads brown's. Docs fixed: global router line, this repo's
      `CLAUDE.md` (CURRENT STATE block), `mcp/wiki/concepts/oauth-model.md`, homeLab
      `vm101-ubuntu.md`, brain `gsuite-external-published-unverified`.
      ONLY THING LEFT — the day-8 proof: on or after **2026-10-14**, both must still
      answer without a reauth (any `mcp__gsuite-jaded__*` / `mcp__gsuite-brown__*`
      read). Alive → flip this `[x]` and drop the "Weekly auto-reauth script" item
      below. `invalid_grant` → the claim is wrong: "Make internal" on `mcps` and
      build the second project for the Gmail accounts.
      The "Plan" bullet below (a NEW project) is superseded by this.
      Idea captured mid-thought, not yet looked into further. Reasoning + the
      three-state table: brain `gsuite-external-published-unverified`.
      • Why now: `gsuite-jaded` still rides Desktop client `664420379329-…` in
        `ancient-sunspot-471815-g9` (live, per `check-oauth.sh` 2026-10-05). The June
        notes call it "the Elevated project" — UNCONFIRMED who owns it. First check:
        does it show in the console project picker as jaded423@gmail or j@jadedviber?
        If yes → just publish it as is. If it is Elevated's, Joshua has had no access
        since 2026-09-30 and it dies if anyone there deletes it → rebuild as below.
        `gsuite-brown` is not in `check-oauth.sh`'s roster; assumed same client — check.
      • Plan: NEW project under the jadedviber.com org, owned by j@jadedviber.com (not
        `mcps` — its consent screen is Internal, one screen per project; not the
        personal `danger-zone-007`) → consent screen **External** → **Publish app**
        (In production, do NOT submit verification) → Desktop client →
        `setup-org-clients.sh jaded=… brown=…` (add brown to both scripts' rosters)
        → reauth each once.
      • UNTESTED claim to prove: an unverified in-production app with restricted Gmail
        scopes keeps its refresh token past 7 days (cost: one "unverified app" screen
        per auth, 100-user cap). Test = reauth one account, confirm alive on day 8.
        Fallback is "Back to testing".
      • When proven: fix `CLAUDE.md` → "Multi-org OAuth architecture" and
        `mcp/wiki/concepts/oauth-model.md` (both only weigh Testing vs full CASA
        verification), and the "External-Testing → weekly reauth" router line.
      verify: ./check-oauth.sh | grep -c ancient-sunspot   # 0 = done

- [x] 2026-10-06 — overtaken: no instance rides `ancient-sunspot` any more (verify line = 0); elevated + point4 are deregistered, and j@/jaded/brown share the published `mcps` app (item above). Was: **⏸ SHELVED 2026-06-17 — OAuth migration to per-org Internal apps.**
      Full design + resume runbook live in `CLAUDE.md` → "Multi-org OAuth
      architecture" (see the SHELVED banner at its top). Brain:
      `gsuite-oauth-architecture`.

      **Live state 2026-07-28** (`./check-oauth.sh`) — the migration is PARTLY DONE,
      not the all-shared stop-gap this item used to describe:
      • **elevated** — own client `197560424876-…` in its own project
        `meeting-gsuite-internal`. Already cut over.
      • **point4** + **jaded** — still share the old Elevated Desktop client
        `664420379329-…` in `ancient-sunspot-471815-g9` (External app in Testing).
      All 3 authed, 8 scopes each, Joshua has live access to every mailbox.
      *(Not verified from the CLI: whether elevated's consent screen is actually set
      to Internal. Confirm in the console before calling that leg finished.)*

      **Why still deferred:** the remaining split is piecewise — point4 loses access
      until its own Internal client is built + consent screen flipped + re-authed.
      Not worth trading a working setup for a half-migrated one right now.

      **Target when resumed:** per-org **Internal** OAuth apps (no verification, no
      CASA, no 7-day expiry; Elevated's Internal app auto-covers Cody) + jaded on
      External/Testing. Use `setup-org-clients.sh` (NOT the deprecated
      `remint-oauth.sh`). Branding (JadedViber) + a `danger-zone-007` "tools" Desktop
      client are already staged for the future jaded instance.
      Remaining work = **point4 only**; jaded stays External by design.

      **Kept, NOT shelved:** dir rename `~/.config/gsuite` → `~/.config/gsuite-elevated`
      (agnostic naming; `install.sh`, `setup-org-clients.sh`, `check-oauth.sh`,
      `remint-oauth.sh`, and all MCP registrations already point at it).
      verify: ./check-oauth.sh | grep -c 'project=ancient-sunspot'   # 0 == cutover done

- [ ] **Weekly auto-reauth script — GATED on the per-org cutover above; jaded-only.**
      Once point4 joins elevated on an Internal app (no token expiry), only the
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
      cheap holdout fix. Don't build until point4 cuts over (no point scripting the
      script's own gate away).

- [ ] **Bug: `check-oauth.sh` has a bash shebang but breaks under `sh`** (`line 17:
      elevated: unbound variable` — associative arrays). Either it's only ever run as
      `./check-oauth.sh`/`bash check-oauth.sh` (fine, low prio) or add a `sh`-safe
      guard. Same risk in `setup-org-clients.sh` (also uses `declare -A`).

- [ ] **Contacts / People resolve tool** (`people_search`, name→address — e.g. "Cody"
      → cody@elevatedtrading.com). Draft-to-name is constant friction. **Cost: NEW People
      API scope = OAuth re-consent on all 3 instances.** Decide if worth the re-auth.

- [ ] **`gmail_get_thread` follow-ons** (optional): whole-thread attachment index;
      mark-read / archive / star verbs — reachable NOW via `gmail_batch_modify` + system
      label IDs (UNREAD / INBOX / STARRED), and `gmail_list_labels` (added 2026-07-08) makes
      those IDs discoverable. Only add dedicated verbs if the batch_modify path proves clumsy.

- [x] **`gmail_list_drafts` — find existing drafts** (added 2026-09-29). Search drafts
      with Gmail query syntax → {draft_id, message_id, thread_id, to, subject, snippet,
      attachments}. The missing handle: today I can only edit drafts I created myself.
      Origin: Joshua's hand-started reply to Ollie (Be Well offer) — couldn't strip the
      two carried-over signature logos because no tool could find the draft's id.
- [x] **`gmail_edit_draft` — surgical in-place draft edit** (added 2026-09-29). Fetch the
      draft's raw MIME, change ONLY what's asked (remove attachments by filename, add
      local/Drive attachments, find→replace text in plain+HTML parts, set To/Cc/Bcc/
      Subject), write it back. Keeps the formatted quote, threading headers, inline
      parts. `gmail_update_draft` = full rebuild, which is what would have mangled
      Ollie's quoted email.
- [x] **`drive_upload_file` — binary upload from a local path** (added 2026-09-29).
      `drive_create_file` is text-only; uploading the signed offer PDF needed a
      carrier-draft workaround (attach → `gmail_get_attachment` drive_folder_id → delete).
      done 2026-09-29: all three built + live-verified on gsuite-brown (Ollie draft logos
      removed in place; test PNG uploaded + soft-deleted). See changelog.

> Completed items archived → [graveyard/TODO-archive.md](graveyard/TODO-archive.md).
