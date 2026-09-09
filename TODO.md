# gsuite TODO

- [ ] **Cynthia install follow-up + streamline INSTALL.md before Cody's install.** (added 2026-08-31)
      Cynthia set up 2026-08-31 on Claude Desktop + CLI (Ghostty); Gmail working.
      Remaining: enable her non-gmail features (`gsuite features enable …` + re-run
      `gsuite auth` — the gmail-only first pass was the default flags, not a bug),
      review her session transcript for install friction (GitHub account detour,
      Ghostty/CLI bootstrap), fold fixes into INSTALL.md.
      resume: 2026-09-09 INSTALL.md restructured for Cody's install — read-all/draft-only
      profile (§0/§4/§7/§8), stale `pip install -e ./gsuite` fixed, 3-check verify,
      trust ladder. Still open: Cynthia's non-gmail features + her transcript review.

- [ ] **⏸ SHELVED 2026-06-17 — OAuth migration to per-org Internal apps.**
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

> Completed items archived → [graveyard/TODO-archive.md](graveyard/TODO-archive.md).
