---
type: reference
title: gsuite — Google Workspace MCP (main reference)
tags: [gsuite, google-workspace, gmail, drive, oauth, mcp, reference]
related: [index, changelog, design-and-history]
---

# gsuite — in-house Google Workspace MCP

> **Stack:** Tier-2 leaf. Parent hub: [mcp](../mcp/CLAUDE.md) (`~/projects/mcp`). Router: [global](~/.claude/CLAUDE.md). A leaf orchestrates nothing → no `wiki/` tree (typed docs in `docs/` instead).

**Status:** Fully shipped and live — all phases done; `@gongrzhe`/`@piotr-agier` retired. Renamed `gspace` → **`gsuite`** 2026-06-15 and flattened out of the `mcp/` meta-repo to its own repo root (`~/projects/gsuite`).
**Owner:** Joshua Brown

> **This is the current-state reference** — the live auth model, feature-flag/scope
> mechanics, and multi-org OAuth setup. Pointers for everything else:
> - **Live tool roster** — run `gsuite tools` (or `--json`); the code registry is the
>   source of truth, no hand-kept list. Count + catalog: [docs/index.md](docs/index.md)
>   (**63 tools / 16 feature flags** as of 2026-07-08).
> - **Version history** — [docs/changelog.md](docs/changelog.md).
> - **The "why" (original design proposal + phase build-log), plus the Gmail-filter-engine
>   gotchas** — [docs/design-and-history.md](docs/design-and-history.md). Those gotchas
>   (negatedQuery coordination, 1000-ID batch cap, label→ID resolution) are still
>   authoritative even though they live in the archive.

## Feature flags + scope management

This is the big idea: **you control what the MCP can do via a settings file, and the MCP re-requests OAuth scopes to match.** No GCP console visits after initial setup.

### How it works

1. **One-time GCP setup:** OAuth consent screen has _all_ scopes we might ever want pre-approved (user = test user). Already done today for the "Claude" client (Drive, Docs, Sheets, Slides, Calendar, Tasks, Drive Activity). Next step: add Gmail scopes there too.

2. **Runtime control** via `~/.config/gsuite[-acct]/settings.json`:

```json
{
  "features": {
    "gmail.read": true,
    "gmail.send": false,
    "gmail.filters": true,
    "gmail.bulk_modify": true,
    "gmail.classify": true,
    "drive.read": true,
    "drive.write": false,
    "docs": false,
    "sheets": false,
    "calendar": true,
    "tasks": false
  },
  "llm": {
    "model": "claude-haiku-4-5-20251001",
    "classify_max_tokens": 256
  }
}
```

3. Each feature maps to scopes:

```python
FEATURE_SCOPES = {
    "gmail.read":        ["https://www.googleapis.com/auth/gmail.readonly"],
    "gmail.send":        ["https://www.googleapis.com/auth/gmail.send"],
    "gmail.filters":     ["https://www.googleapis.com/auth/gmail.settings.basic"],
    "gmail.bulk_modify": ["https://www.googleapis.com/auth/gmail.modify"],
    "drive.read":        ["https://www.googleapis.com/auth/drive.readonly"],
    "drive.write":       ["https://www.googleapis.com/auth/drive"],
    ...
}
```

(Full, current mapping lives in `gsuite/settings.py::FEATURE_SCOPES`; read/write features
collapse to ~9 OAuth scopes via subsumption.)

4. **On server start:** MCP diffs current token scopes vs. enabled features. If gap, it prints a message "Run `gsuite auth` to refresh tokens with new scopes" and disables affected tools gracefully.

5. **`gsuite auth`** command: runs browser OAuth flow, requesting the union of scopes from all enabled features. New tokens cached, MCP restarts transparently.

6. **Tool registry respects flags:** at server startup, only tools whose features are enabled get registered. Turning off `gmail.send` hides every send-related tool from Claude — the tool simply doesn't exist that session.

### Two ways to change settings

| Method | When to use |
|---|---|
| `gsuite features enable gmail.send` (CLI) | You know exactly what you want; scripts, docs, teammates |
| `settings` MCP tool callable from Claude | Conversational: "Claude, turn on Gmail sending" — Claude edits settings.json, asks you to run `gsuite auth` |

Either way, **nothing changes without re-auth**. The browser flow is the confirmation step — Google shows the new scope list, you click Allow, tokens refresh.

### Why this is safe

- The MCP can only *request* scopes. It cannot self-elevate — Google shows you the consent screen with the exact scope list each time you re-auth.
- `settings.json` is user-editable, outside the MCP's code path. Breaking it doesn't break the server; it just disables features.
- `tokens.json` is written with 0600 permissions.
- Revoking access is a one-click operation at https://myaccount.google.com/permissions — independent of the MCP.

## Multi-org OAuth architecture (2026-06-17) — Internal per Workspace + Testing for jaded

> **⏸ SHELVED 2026-06-17 — NOT the current state. Stop-gap in effect.**
> The split below is the *target*, deferred. **Current working state:** all four
> accounts (`gsuite-{elevated,dax,point4,jaded}`) share the ONE Elevated Desktop
> client `664420379329-…` in project `ancient-sunspot-471815-g9`, on a single
> **External app in Testing**. All four are authed and connected *today* — Joshua
> has live access to every mailbox, and Cody can use it now by clicking through the
> "unverified app" warning once.
>
> **Why shelved, not executed:** migrating to per-org Internal apps is a piecewise
> cutover — each account loses access until *its* new Internal client is built,
> consent screen flipped Internal, and re-authed. Joshua has full multi-mailbox
> access right now and won't trade a working setup for a half-migrated one. The
> External/Testing stop-gap is good enough: Cody eats the one-time unverified
> message, everyone works today. Revisit when there's appetite for the cutover.
>
> **Already built toward the target (don't redo):** dir rename to
> `~/.config/gsuite-elevated` (agnostic naming, all scripts + MCP registrations
> updated, **kept — not shelved**); `setup-org-clients.sh` / `enable-apis.sh` /
> `check-oauth.sh` helpers; the **JadedViber** consent-screen branding + a Desktop
> "tools" client in personal project `danger-zone-007` (reserved for the future
> jaded External instance); jadedviber.com `/app/`, `/privacy/`, `/terms/`, logo.
> `remint-oauth.sh` is DEPRECATED — the target uses `setup-org-clients.sh`.
> Resume point: the "Per-org setup runbook" below.

**Decision (target, deferred).** Do NOT pursue full Google OAuth verification for
one shared External app. Instead give each Workspace account its own **Internal**
OAuth app, and keep the one consumer account (jaded) on an **External app in
Testing** mode.

**Why.** The requested scope set includes RESTRICTED scopes (`gmail.modify`,
`gmail.settings.basic`). Full verification of an External app with restricted
scopes requires a demo video PLUS an annual third-party **CASA** security
assessment (~$540–4,500/yr) AND is still subject to the 100-user cap until
approved. **Internal** apps (owned by a Workspace org, usable only by that org's
users) need **none of that** — no verification, no video, no CASA, no user cap,
and refresh tokens **do not** expire after 7 days. Restricted Gmail scopes are
allowed Internal. This is strictly better for a multi-org personal toolset.

| Account | Google type | OAuth model | GCP project | Notes |
|---|---|---|---|---|
| elevated | Workspace (elevatedtrading.com) | **Internal** | (own) | Covers **Cody** automatically — he's @elevatedtrading.com |
| dax | Workspace (daxdistro.com) | **Internal** | (own) | |
| point4 | Workspace | **Internal** | (own) | |
| jaded | consumer (jaded423@gmail.com) | **External / Testing** | personal (e.g. danger-zone-007) | Can't be Internal (no org). Sole test user = you. Token expires ~7 days of non-use → just re-auth on next use; no reminder wanted. |

**Current live state (per `./check-oauth.sh`, 2026-06-17):** ALL FOUR dirs still
share ONE Desktop client `664420379329-…` in the **Elevated** project
`ancient-sunspot-471815-g9`. The planned remint to `danger-zone-007`
(`remint-oauth.sh`) was never executed. So today the whole toolset rides
Elevated's GCP on a single External app — the configuration that triggers the
verification wall. Granted scopes (live): gmail.modify, gmail.send,
gmail.settings.basic, drive, documents, spreadsheets, presentations, calendar,
tasks.

**Target end state:** four DISTINCT clients, one per dir, three Internal + jaded
Testing. `setup-org-clients.sh` (NEW) installs a distinct client per dir and
supersedes the single-client `remint-oauth.sh`.

### Per-org setup runbook
For each of elevated, dax, point4 (in that org's own GCP project):
1. `./enable-apis.sh <PROJECT_ID>` — enables the 7 APIs (gmail, drive, docs,
   sheets, slides, calendar-json, tasks).
2. Console → OAuth consent screen → **User type: Internal**. App name **JadedViber**
   (must match across all). Home page `https://jadedviber.com/app/`, privacy
   `/privacy`, terms `/terms`, logo `~/projects/jadedViber/snek-logo.png`.
3. Console → Credentials → Create OAuth client ID → **Desktop app**. Download JSON.
4. Repeat per org. Then install all at once:
   `./setup-org-clients.sh elevated=el.json dax=dax.json point4=p4.json`
5. jaded: in its personal project, set publishing status **Testing**, add
   jaded423 as a test user, create a Desktop client, then
   `./setup-org-clients.sh jaded=jaded.json`.
6. Verify: `./check-oauth.sh --apis` — confirm each account points at its OWN
   project and scopes match.

### Drift risk + guardrail
Scopes themselves live in `gsuite/settings.py` (same code → identical scope
requests), so they don't drift. What CAN drift per project: enabled APIs,
consent-screen branding, client creds. `check-oauth.sh` is the drift guardrail —
run it after any change; each account should show a DIFFERENT project_id once
migrated.

### Helper scripts (this repo)
- `setup-org-clients.sh` — install a distinct OAuth client per account dir + reauth.
- `enable-apis.sh <PROJECT>` — enable the 7 required APIs in a project.
- `check-oauth.sh [--apis]` — drift/status report across all 4 dirs.
- `remint-oauth.sh` — DEPRECATED single-client installer (kept for history).

### jadedViber site (done 2026-06-17)
Branding assets shipped to jadedviber.com (GitHub Pages, plain HTML):
`/app/` (OAuth home page, H1 "JadedViber", explains purpose + scopes),
`/privacy/`, `/terms/` (limited-use disclosure), and `snek-logo.png` (512×512
mascot on #0a0a0a — transparent snek.png rendered white on Google's consent card).

### Status check — 2026-06-23 (still on the stop-gap)

The per-org Internal migration above remains **shelved/deferred**. Live state is
still the single External/Testing client. Tokens still die ~7 days in Testing mode
— that part stands, and a batch re-auth was run today (token mtimes all 2026-06-23).

**CORRECTION (2026-06-23 PM) — earlier root-cause diagnosis was WRONG.** The
"Sign in — continue to Elevated" popup-on-Claude-Code-startup was **NOT** gsuite.
`gsuite serve` **cannot** open a browser — `auth.py` only calls `run_local_server(
open_browser=True)` from the `gsuite auth` CLI, never from `serve`; on a stale token
`serve`→`get_credentials`→`creds.refresh()` raises `invalid_grant`, it does not prompt.
The earlier session was told a token "expired yesterday" and assumed gsuite checks/
re-auths on startup — it does not.

**Actual cause:** two LEGACY Google MCPs were still registered top-level in
`~/.claude.json` long after gsuite replaced them (Phase 4/5) — `gmail`
(`@gongrzhe/server-gmail-autoauth-mcp`, name = *autoauth*) and `google-drive`
(`@piotr-agier/google-drive-mcp`, does Docs/Sheets/Slides = the popup's scope ask).
Both are `npx` (unpinned → silent version bumps) and **auto-launch a browser OAuth
flow on startup** when their own token is stale. Every Claude session spawned them;
a full close-out + reboot cold-started them all at once → browser popup. Hidden in
steady-state because sessions were left running for days. **Fix applied:**
`claude mcp remove gmail` + `claude mcp remove google-drive`. gsuite's 4 instances
+ claude.ai hosted connectors fully cover Gmail/Drive/Docs/Sheets/Slides/Calendar.

The recurring chore until migration (gsuite tokens, real ~7-day Testing expiry):

```bash
for a in elevated jaded point4; do
  GSUITE_CONFIG_DIR=~/.config/gsuite-$a /Users/j/projects/gsuite/.venv/bin/gsuite auth
done   # pick the matching account in the chooser each time
```
> **dax removed 2026-07-06** — Dax Distro dissolved; `gsuite-dax` instance detached,
> config dir graveyarded, dropped from `install.sh` + `setup-org-clients.sh`. See
> `~/projects/graveyard/dax-teardown-2026-07/`.

Per-account staleness this round: dax was 8d (already dead), jaded 6d, elevated/
point4 ~1d. Re-auth order should lead with the oldest.

### Cost to take `jaded` off the weekly-refresh treadmill

`jaded423@gmail.com` is a **consumer** account → can't be Internal (Internal needs
a Workspace org, and orgs need a domain — a @gmail.com can't be "converted").
Options costed 2026-06-23:

- **Google Workspace Business Starter** — ~$7/user/mo (~$84/yr) on a domain you own
  (e.g. jadedviber.com). Has Gmail, so it satisfies the jaded MCP's `gmail.modify`/
  `gmail.send` scopes. **But** it creates a NEW identity (`you@jadedviber.com`), not
  jaded423@gmail.com — you'd migrate/forward the personal mailbox into it or point
  the MCP at the new address.
- **Cloud Identity Free** — $0, managed org + Internal OAuth on a domain, but **no
  Gmail mailbox** → can't serve the gmail scopes → dead end for this profile.

**Verdict:** ~$84/yr + a mailbox migration to kill ONE weekly popup. Not worth it
unless jadedviber.com email is wanted anyway. Cheaper holdout fixes: keep weekly-
refreshing just jaded, or drop its restricted scopes (`gmail.modify`/`drive`-write)
so it can publish to Production free with no token expiry. The 3 Workspace accounts
(elevated/dax/point4) remain the real win — Internal-eligible, permanent fix.
