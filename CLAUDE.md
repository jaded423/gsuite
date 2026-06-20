# gspace — in-house Google Workspace MCP

**Status:** Phases 1–3 shipped; Phase 4 migration ready (2026-04-16)
**Owner:** Joshua Brown
**Working name:** `gspace` (open to change)

## Why build this

We already use two MCPs for Google Workspace (`@gongrzhe/server-gmail-autoauth-mcp` for Gmail, `@piotr-agier/google-drive-mcp` for Drive/Docs/Sheets/Slides/Calendar) plus the claude.ai hosted Gmail/Calendar/Drive connectors. They cover the basics, but we keep hitting their ceilings:

1. **Bug: `@gongrzhe` list_filters returns empty** even with `gmail.settings.basic` scope granted. Verified via direct API — 28 filters exist, MCP can't see them. Upstream inactive. Blocker for filter-management workflows.
2. **No "bulk reclassify existing emails" tool.** Gmail filters only apply to new mail. When we tightened the Billing filters, ~200 existing emails stayed misclassified. Had to write throwaway Python each time.
3. **No declarative rule model.** A common case: "route this sender to CS, EXCEPT when the subject says 'Thank you' — those go to Billing." Today that's 3 scattered Gmail filters with hand-tuned `negatedQuery` strings. A rule DSL would express it as one.
4. **No LLM-assisted classification.** "Statement vs invoice" can't be done with regex. Reading the email body is needed. Nothing in the current stack does this.
5. **No backup/restore workflow.** Filter edits are destructive (Gmail filters are immutable — edit = delete + recreate). We backed up manually each time.
6. **Scope sprawl.** Two OAuth clients, each with half the coverage, on the same GCP project. Can consolidate under the "Claude" client we set up today.
7. **Control.** In-house means we can add tools tailored to our workflows (Fathom → ClickUp task sync, meeting → email follow-up drafts, etc.).

## Architecture (proposed)

```
~/projects/mcp/
├── CLAUDE.md                     # This file — source of truth
├── pyproject.toml                # Python packaging
├── README.md → CLAUDE.md         # symlink
├── gspace/
│   ├── __init__.py
│   ├── server.py                 # MCP server entry (stdio transport)
│   ├── auth.py                   # OAuth client + automatic token refresh
│   ├── settings.py               # Feature flags + scope mapping
│   ├── tools/
│   │   ├── __init__.py           # Tool registry; loads enabled tools from settings
│   │   ├── gmail_filters.py      # list/create/replace/backup/restore filters
│   │   ├── gmail_bulk.py         # batch modify / reclassify existing mail
│   │   ├── gmail_rules.py        # declarative rule engine
│   │   ├── gmail_classify.py     # LLM-assisted categorization
│   │   ├── drive.py              # (later) Drive ops
│   │   ├── docs.py               # (later)
│   │   ├── sheets.py             # (later)
│   │   └── calendar.py           # (later)
│   ├── rules/
│   │   ├── engine.py             # Parse + evaluate YAML rules
│   │   └── examples/
│   │       └── elevated.yaml     # Our current Gmail routing as a ruleset
│   └── cli.py                    # `gspace` CLI (auth, status, features)
└── tests/
    ├── test_auth.py
    ├── test_gmail_filters.py
    └── fixtures/

~/.config/gspace/
├── settings.json                 # Feature flags (editable)
├── oauth-client.json             # Copied from the "Claude" GCP OAuth client (Desktop type)
└── tokens.json                   # Refresh/access tokens (0600)
```

### Language: Python
- We're already using it for the one-off API scripts.
- `google-api-python-client` is mature and covers every Google API we care about.
- Anthropic's `mcp` Python SDK is stable and clean.
- No reason to introduce a second runtime.

### Transport: stdio
- Claude Code spawns the server as a subprocess — no network surface, simpler security.
- Streamable HTTP transport can be added later if we need shared access across machines.

## Feature flags + scope management

This is the big idea: **you control what the MCP can do via a settings file, and the MCP re-requests OAuth scopes to match.** No GCP console visits after initial setup.

### How it works

1. **One-time GCP setup:** OAuth consent screen has _all_ scopes we might ever want pre-approved (user = test user). Already done today for the "Claude" client (Drive, Docs, Sheets, Slides, Calendar, Tasks, Drive Activity). Next step: add Gmail scopes there too.

2. **Runtime control** via `~/.config/gspace/settings.json`:

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

4. **On server start:** MCP diffs current token scopes vs. enabled features. If gap, it prints a message "Run `gspace auth` to refresh tokens with new scopes" and disables affected tools gracefully.

5. **`gspace auth`** command: runs browser OAuth flow, requesting the union of scopes from all enabled features. New tokens cached, MCP restarts transparently.

6. **Tool registry respects flags:** at server startup, only tools whose features are enabled get registered. Turning off `gmail.send` hides every send-related tool from Claude — the tool simply doesn't exist that session.

### Two ways to change settings

| Method | When to use |
|---|---|
| `gspace features enable gmail.send` (CLI) | You know exactly what you want; scripts, docs, teammates |
| `settings` MCP tool callable from Claude | Conversational: "Claude, turn on Gmail sending" — Claude edits settings.json, asks you to run `gspace auth` |

Either way, **nothing changes without re-auth**. The browser flow is the confirmation step — Google shows the new scope list, you click Allow, tokens refresh.

### Why this is safe

- The MCP can only *request* scopes. It cannot self-elevate — Google shows you the consent screen with the exact scope list each time you re-auth.
- `settings.json` is user-editable, outside the MCP's code path. Breaking it doesn't break the server; it just disables features.
- `tokens.json` is written with 0600 permissions.
- Revoking access is a one-click operation at https://myaccount.google.com/permissions — independent of the MCP.

## Tool catalog (v1 scope)

### Gmail — filter management (fills the `@gongrzhe` gap)

- `gmail_list_filters` — paginated, resolves label IDs to names, returns rich objects
- `gmail_get_filter(id)` — full detail
- `gmail_create_filter(criteria, action)` — with friendly criteria builder
- `gmail_replace_filter(id, criteria, action)` — delete + recreate atomically
- `gmail_delete_filter(id)` — with confirm flag
- `gmail_backup_filters(path)` — JSON export of all filters + label name resolution
- `gmail_restore_filters(path, mode)` — from backup; modes: replace-all, merge, dry-run

### Gmail — bulk ops (the "apply filter to existing mail" gap)

- `gmail_reclassify(filter_id)` — find existing mail matching a filter's criteria and apply its actions (the thing we wrote by hand today)
- `gmail_batch_modify(query, add_labels, remove_labels)` — general-purpose batch label op
- `gmail_move_label(from_label, to_label, query)` — move all mail in one label to another (optionally scoped by query)

### Gmail — declarative rules

- `gmail_apply_rules(yaml_path)` — reads a YAML ruleset, creates/updates filters to match, optionally reclassifies existing mail. Idempotent — safe to re-run.

Rule syntax sketch:

```yaml
rules:
  - name: key-customer
    match:
      from: [sales@customer-a.example.com, sales@customer-b.example.com]
    route:
      - if: "subject contains 'Thank you'"
        to: Billing
      - else:
          to: Customer Service

  - name: vendor-notifications
    match:
      from: no-reply@notifications.vendor.example.com
    route: {to: Vendor}
    except_in: Billing       # Negate from Billing's filter

  - name: billing-receipts
    match:
      subject_any_of:
        - Payment confirmation
        - Thank You for Your Payment
        - Your payment has been processed
    actions: {mark_read: true}
```

The engine compiles this down to a set of Gmail filters with the right `negatedQuery` coordination (the limitation hit in vanilla Gmail: can't remove user labels from filters, so source filters need `except_in` negation). Compiling a ruleset to filters is the key abstraction; it's what makes the "exception" case a one-liner instead of three filter rewrites.

### Gmail — LLM classification

- `gmail_classify_message(id, categories)` — reads body, returns best-fit category + confidence
- `gmail_classify_label(label, categories, apply=False)` — scan every message in a label, propose reclassification, optionally apply

Uses Haiku 4.5 for speed/cost. Tool args let caller override model.

Example use: run `gmail_classify_label("Billing", ["bill", "statement", "receipt", "marketing", "other"])` once a week to catch things regex misses ("Statement from Dallas Janitorial" is a statement, "Statement of Work" might not be).

### Drive / Docs / Sheets / Calendar (v2, later)

Keep `@piotr-agier/google-drive-mcp` running side-by-side for these until our needs outgrow it. When we do rebuild, same auth client.

## Key learnings from the filter-management session (2026-04-16)

Capture these upfront so the build doesn't re-learn them:

1. **Gmail filters cannot remove user labels.** `removeLabelIds` only accepts system labels (INBOX, UNREAD, SPAM, STARRED, IMPORTANT, CATEGORY_*). To move mail out of label X, the filter that adds X must have a `negatedQuery` excluding the target pattern. Our rule engine must handle this coordination.

2. **Filter criteria stored verbatim.** UI-created filter with `subject:("[Billing]")` is stored literally as `"subject": "(\"[Billing]\")"`. Our filter detection/matching code must handle both literal-match and parsed-value comparisons.

3. **Full filter IDs are long (~70 chars).** `list_filters` returns IDs like `ANe1BmhCiBTYYMHKmdXlaSR40oUuirL-GTglNQec8v0iYqugSCbT1ki_NjNcO38OiAMt2eSI8w`. Don't truncate when storing for later use.

4. **Token refresh is a recurring gotcha.** The @gongrzhe MCP's cached token went stale and its `list_filters` appeared to silently return empty (actually a separate bug, but diagnostic noise). Our auth layer must refresh proactively when within 5 min of expiry, and any tool that hits the API must catch 401 and retry once with fresh token.

5. **Gmail batchModify accepts 1000 IDs per call.** Chunk appropriately for bulk ops.

6. **Google Groups routing affects filter matching.** An email sent to `billing@example.com` (a Google Group) arrives at group members with `To:` still set to the group address — so `to:billing@...` filters match. This enables a "one filter per inbox" approach.

7. **`negatedQuery` is a single Gmail search query, OR-combined against criteria.** Complex exclusions (e.g., "exclude this vendor's marketing mail except 'Thank you' orders") must be expressed in Gmail search syntax, not as separate fields. The rule compiler generates this correctly.

8. **Batch modify runs against query results synchronously** but label changes in Gmail can take a second or two to become visible in subsequent searches (eventual consistency). Tests need brief delays or retries.

9. **Always back up before destructive ops.** Filter edits are delete + recreate. Take a full JSON dump first, write to timestamped file.

10. **Label name → ID resolution is needed everywhere.** Cache the label map at server start; refresh on label create/delete events.

## Migration plan

Phase 0 — planning (this file). Done.

Phase 1 — core + filter management
1. Scaffold package, pyproject.toml, stdio server
2. Auth layer: OAuth client reuse from `~/.config/google-drive-mcp/gcp-oauth.keys.json` (same "Claude" client); add Gmail scopes to consent screen in GCP console
3. Settings system (feature flags + scope mapping)
4. `gspace auth` / `status` / `features` CLI
5. Gmail filter tools (list/get/create/replace/delete/backup/restore)
6. Test against current 36 filters — must match what we see in the UI

Phase 2 — bulk ops + rules
7. Bulk modify / reclassify / move-label tools
8. Rule engine (YAML → filter set compiler)
9. Export current Gmail config as `rules/elevated.yaml` (reverse-engineering step — validates the rule language covers the real cases)

Phase 3 — LLM classification
10. Classify single message / whole label
11. Prompt caching, Haiku model default
12. Integration: `classify_label` + `bulk_modify` to auto-fix mis-sorts on a schedule

Phase 4 — retire old MCPs
13. Move settings from `~/.gmail-mcp/` into `~/.config/gspace/`
14. Run side-by-side for a week; diff behavior
15. Remove `@gongrzhe/server-gmail-autoauth-mcp` from `claude mcp list`

Phase 5 — Drive/Docs/Sheets/Calendar
16. Port the tools we actually use from `@piotr-agier/google-drive-mcp`
17. Specialized tools (Fathom→Sheet import, meeting-to-calendar, etc.)
18. Retire `@piotr-agier/google-drive-mcp`

## Robustness requirements

- **Automatic token refresh** with a 5-minute safety margin; retry on 401.
- **Rate limiting** against Gmail API quotas: 250 quota units/sec/user, ~1 billion/day. Conservative client-side: 5 req/sec sustained, with burst allowance. Back off on 429.
- **Structured logging** to stderr (MCP reserves stdout for protocol). Levels: debug, info, warn, error. Default info.
- **Backups before destructive ops** — any `replace_filter` / `delete_filter` / `apply_rules` writes a pre-change snapshot to `~/.config/gspace/backups/YYYY-MM-DDTHH-MM-SS.json`. Keep 30 days.
- **Dry-run mode** — `gmail_apply_rules(yaml_path, dry_run=True)` shows what it _would_ change without applying.
- **Idempotency** — re-running rule apply produces the same filter set (no duplicates). Achieved by hashing criteria as a dedup key.
- **Tests** — pytest, with a mock Gmail API (not real calls). Coverage target: auth, rule compiler, bulk ops. Integration tests run against a dedicated test account (not the real one).
- **Error surface** — tool errors return structured `{error: "msg", retryable: bool, docs: "url"}` objects, not raw exceptions.

## Open questions

1. **Naming.** ~~`mcp-elevated`~~ **Renamed to `gspace` on 2026-04-17** (post-Phase-5). Shorter than `workspace-mcp`, unambiguous about the Google Workspace scope, matches the `g*` convention of other Google CLIs (`gcloud`, `gsutil`, `gh`). The original package lives side-by-side at `~/projects/mcp/mcp_elevated/` during burn-in; it will be removed once `gspace` is verified in production.
2. **Package distribution.** Install locally (`pip install -e .`) or publish to PyPI as `gspace`? Local-only is simpler; publishing opens up community contribution.
3. **Open source?** Nothing in here is ET-specific _except_ the example ruleset. Could open-source the core and keep the ruleset private. Would help with the MCP ecosystem.
4. **Rule language format.** YAML is readable but has gotchas (quoting, types). Alternatives: TOML (less expressive), a custom DSL (more work), Python (max flexibility, less safe).
5. **Claude Code vs. generic MCP client.** The `settings` tool pattern assumes a chat UI. For non-interactive clients (scripts), the CLI path is what matters. Both should work.
6. **Fathom, ClickUp integration.** Out of scope for v1, but the architecture should accommodate — probably as separate tool modules that use their own auth.

## Related memory

- `~/.claude/projects/-Users-j/memory/MEMORY.md` has pointers to our filter-management session learnings.
- Gmail filter backup from 2026-04-16: `~/.gmail-mcp/filter-backup-2026-04-16-142727.json` (34 filters pre-cleanup).
- Current filter set (36): accessible via direct API; export to `rules/elevated.yaml` during Phase 2.

## Shipped state (2026-04-16)

Package lives at `~/projects/mcp/gspace/gspace/`. Installed editable into `~/projects/mcp/gspace/.venv`. Config at `~/.config/gspace/` (settings.json, oauth-client.json, tokens.json, backups/).

**14 tools registered across 3 feature flags:**

| Feature | Tools |
|---|---|
| `gmail.filters` | `gmail_list_filters`, `gmail_get_filter`, `gmail_create_filter`, `gmail_replace_filter`, `gmail_delete_filter`, `gmail_backup_filters`, `gmail_restore_filters`, `gmail_apply_rules`, `gmail_export_rules` |
| `gmail.bulk_modify` | `gmail_batch_modify`, `gmail_reclassify_filter`, `gmail_move_label` |
| `gmail.classify` | `gmail_classify_message`, `gmail_classify_label` |

Additional feature flags exist (`drive.read/write`, `docs`, `sheets`, `slides`, `calendar`, `tasks`, `gmail.read`, `gmail.send`) — scopes pre-granted, tools to land in Phase 5.

Rule engine: `gspace/rules/engine.py` + starter `rules/examples/elevated.yaml`. Compiles match/route/if-else/except_in/actions into Gmail filter bodies; idempotent via sha1(criteria+action).

Classification: Haiku 4.5 with prompt caching on the system prompt. Tested against a live Billing message — returned `invoice @ 0.95`.

## Phase 4 — retire `@gongrzhe/server-gmail-autoauth-mcp`

**Parity matrix:**

| @gongrzhe tool | gspace equivalent | Notes |
|---|---|---|
| `list_filters` | `gmail_list_filters` | Was broken upstream — returns 36 now |
| `get_filter` | `gmail_get_filter` | |
| `create_filter` | `gmail_create_filter` | |
| `delete_filter` | `gmail_delete_filter` | Auto-backup added |
| `search_emails` | (use claude.ai Gmail connector or Drive search) | Not re-implementing |
| `read_email` / `send_email` / `draft_email` | (use claude.ai Gmail connector) | Hosted connector is stable |
| `batch_modify_emails` | `gmail_batch_modify` | Chunked to 1000/batch |
| `batch_delete_emails` | — | Not needed for our workflows; trivial to add |
| `create_label` / `delete_label` / `update_label` | — | Use Gmail UI; tiny feature |
| `create_filter_from_template` | (use `gmail_apply_rules` with YAML) | Upgrade path |

Everything we actually used in the 2026-04-16 session is covered. Filter management is strictly better (the list bug is gone; backup/restore/bulk-reclassify are net-new).

**Migration steps:**

1. Register the new server in Claude Code:
   ```
   claude mcp add gspace /Users/j/projects/mcp/.venv/bin/gspace serve
   ```
   (Re-launch any existing Claude Code sessions after registration.)
2. Run side-by-side for a week. Both servers are independent (different OAuth clients, different on-disk config trees).
3. When confident, remove the old server:
   ```
   claude mcp remove gmail
   ```
4. Delete legacy config:
   ```
   mv ~/.gmail-mcp ~/projects/graveyard/gmail-mcp-$(date +%Y%m%d)
   ```

**Legacy backup preserved:** `~/.config/gspace/backups/legacy-gongrzhe-filter-backup-2026-04-16-142727.json` (34 filters pre-cleanup; the original at `~/.gmail-mcp/` stays put until step 4).

## Next steps

- ~~Phase 5: Drive/Docs/Sheets/Calendar tool port~~ **Shipped 2026-04-17.** 23 new tools across Drive (8), Docs (4), Sheets (4), Slides (4), Calendar (3). Soft-delete pattern via `_delete-later` folder — no tool ever calls `files().delete()`.
- Side-by-side burn-in with `@piotr-agier/google-drive-mcp`. After confidence, retire and remove.
- Fathom → ClickUp task sync; meeting → email follow-up drafts.
- Open-source decision (core is Elevated-agnostic; rulesets stay private).
- Rename `gspace` → `gspace` (deferred until after burn-in).

## Shipped state (2026-04-17 — Phase 5)

**Total: 37 tools across 13 feature flags.**

| Feature | Tools |
|---|---|
| `drive.read` | `drive_search`, `drive_list_folder`, `drive_list_delete_later` |
| `drive.write` | `drive_create_folder`, `drive_rename`, `drive_move`, `drive_share`, `drive_soft_delete` |
| `docs.read` | `docs_read` |
| `docs.write` | `docs_create`, `docs_append_text`, `docs_find_replace` |
| `sheets.read` | `sheets_read_range` |
| `sheets.write` | `sheets_append_rows`, `sheets_update_range`, `sheets_create` |
| `slides.read` | `slides_read` |
| `slides.write` | `slides_create`, `slides_add_slide`, `slides_replace_text` |
| `calendar.read` | `calendar_list_events` |
| `calendar.write` | `calendar_create_event`, `calendar_update_event` |

**Soft-delete pattern:** `drive_soft_delete` moves files to a `_delete-later` folder in My Drive (auto-created, ID cached per process). `drive_list_delete_later` reviews pending items. No tool in the codebase calls `files().delete()` — user empties the folder manually in the Drive web UI.

**Scope consolidation:** the read/write split collapses to 9 OAuth scopes with subsumption (e.g. `auth/documents` covers `documents.readonly`). Legacy `docs: true`-style settings auto-migrate to the `.read` + `.write` pair on load.

**Tests:** 97 passing, 0.5s suite. Every tool has MagicMock-based request-shape assertions — no real API needed to verify the Drive search query, the Docs `batchUpdate` requests, the Calendar event body, etc. Rate-limit + retry tests exercise 429, 5xx, `Retry-After`, and bucket exhaustion without real sleeping.

## Review notes (2026-04-16)

### Size snapshot
~2,900 lines total; ~2,400 Python. Largest modules:
- `rules/engine.py` — 336
- `tools/gmail_classify.py` — 329
- `tools/__init__.py` — 319 (tool registry)
- `tools/gmail_filters.py` — 285
- `tools/gmail_rules.py` — 254
- `tools/gmail_bulk.py` — 243
- `auth.py` — 195
- `settings.py` — 156
- `server.py` — 140
- `cli.py` — 121

### Improvement suggestions

1. **Tests missing.** `tests/__init__.py` is empty. Highest-value mock target is `rules/engine.py` — idempotency (sha1 dedup) and `negatedQuery` coordination are exactly the things that silently break on refactor. Start there before Phase 5.
2. **`tools/__init__.py` at 319 lines is a smell.** Central registries become god-modules. Switch to decorator-based self-registration per tool module before Phase 5 adds Drive/Docs/Sheets/Calendar — otherwise the registry doubles in size.
3. **Verify rate limiting actually exists.** CLAUDE.md lists it as a requirement (5 req/sec sustained, 429 backoff) but it's not obvious from the file layout. A bulk `reclassify_filter` against a 10k-message label will hit quota fast if the limiter isn't wired up.
4. **Name ambiguity.** `gspace` reads as either "Elevated Trading's MCP" or "elevated-privilege MCP" — confusing if open-sourced. `et-workspace` is clearer. Decide before PyPI.
5. **Phase 5 scope discipline.** Drive/Docs/Sheets/Calendar is a large surface; `@piotr-agier/google-drive-mcp` works today. Port tools only when the existing MCP blocks a real workflow, not preemptively.
6. **Structured error contract.** CLAUDE.md specifies `{error, retryable, docs}` error objects — confirm this is enforced uniformly across all 14 tools, not per-tool ad-hoc.

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
