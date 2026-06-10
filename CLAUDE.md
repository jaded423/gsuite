# In-house MCP workspace

This directory hosts one or more in-house Model Context Protocol (MCP) servers
that we build and maintain ourselves. Each server lives in its own subdirectory
with its own Python package, virtualenv, tests, and CLAUDE.md. Shared
conventions (patterns every server should follow) live here.

## Active servers

| Server | Subdir | Purpose | Status |
|---|---|---|---|
| `gspace` | [gspace/](gspace/CLAUDE.md) | Google Workspace — Gmail, Drive, Docs, Sheets, Slides, Calendar | 42 tools, 101 tests. 2026-06-10: added `gmail_search_messages` + `gmail_read_message` (feature `gmail.read`) and `gmail_create_draft` + `gmail_send_message` (feature `gmail.send`, scope repointed to `gmail.modify` so drafts work, default-on). All satisfied by existing `gmail.modify` grant — no re-consent. Retired `mcp-elevated` on 2026-04-17. Runs as 4 per-account instances — see below. |

## Multi-account setup (gspace × 3 Google accounts)

`gspace` runs as **one server instance per Google account**, isolated by the
`GSPACE_CONFIG_DIR` env var (`settings.py` reads it; defaults to
`~/.config/gspace`). Each instance has its own `oauth-client.json` (same
"Claude" GCP Desktop client, reused), `settings.json`, and `tokens.json`.
Set up 2026-06-02 so Claude can search/operate across all three drives from
any project (e.g. "find this file in any of my drives").

| Server (user scope) | Account | Config dir |
|---|---|---|
| `gspace-elevated` | joshua@elevatedtrading.com | `~/.config/gspace` |
| `gspace-dax` | joshua@daxdistro.com | `~/.config/gspace-dax` |
| `gspace-jaded` | jaded423@gmail.com | `~/.config/gspace-jaded` |
| `gspace-point4` | webmaster@point4project.com | `~/.config/gspace-point4` |

All registered at **user scope** (visible in every project). All enable
the full feature set. Tools appear as `mcp__gspace-<acct>__<tool>`.
`gspace-point4` added 2026-06-10 for Point4 outbound mail (drafts/send via the
new compose tools). webmaster's seat is a scoped Workspace admin (Gmail routing
only — not DKIM/auth).

**Multi-account is by separate instances, on purpose.** One shared codebase,
one config dir per account (`GSPACE_CONFIG_DIR`) → write a tool once, all
instances get it on restart. The hard wall between accounts (separate
processes/tokens, so `gspace-elevated` literally cannot touch Dax data) is a
feature given the Z/Dax-split sensitivity. **Option if the need arises:** collapse
to a single server with an optional `account` param per tool that switches
`GSPACE_CONFIG_DIR` at call time. Convenient (one registration, pick account
per call) but sacrifices that isolation — a wrong `account` arg could operate on
the wrong mailbox. Not built; revisit only if managing N instances becomes the
pain point.

**Note:** `gspace-elevated` reuses the original `~/.config/gspace`. A legacy
**project-scoped** `gspace` server (registered under `~/projects/mcp`) also
points at that dir — inside this project both load and double the elevated
tools. Remove it with `claude mcp remove gspace` (run from `~/projects/mcp`).

### Add another account

```bash
ACCT=newname
mkdir -p ~/.config/gspace-$ACCT
cp -p ~/.config/gspace/oauth-client.json ~/.config/gspace-$ACCT/oauth-client.json
chmod 600 ~/.config/gspace-$ACCT/oauth-client.json
# write settings.json (copy an existing one; toggle features as needed)
cp ~/.config/gspace-dax/settings.json ~/.config/gspace-$ACCT/settings.json

# add the account as a Test User on the "Claude" GCP OAuth consent screen first,
# then run the browser auth (pick the right account, click Allow):
GSPACE_CONFIG_DIR=~/.config/gspace-$ACCT ~/projects/mcp/gspace/.venv/bin/gspace auth

# register at user scope, then relaunch Claude Code
claude mcp add gspace-$ACCT -s user -e GSPACE_CONFIG_DIR=~/.config/gspace-$ACCT \
  -- ~/projects/mcp/gspace/.venv/bin/gspace serve
```

Verify which account an instance is authed as (Drive scope, no userinfo scope needed):

```bash
GSPACE_CONFIG_DIR=~/.config/gspace-$ACCT ~/projects/mcp/gspace/.venv/bin/python -c \
  "from gspace import auth; print(auth.build_service('drive','v3').about().get(fields='user').execute()['user']['emailAddress'])"
```

Re-auth a single instance (after enabling new features → new scopes): same
`gspace auth` line with that instance's `GSPACE_CONFIG_DIR`.

## Conventions for any MCP built here

These patterns came out of building `gspace` and are worth carrying forward:

- **Feature flags + scope mapping** (`settings.py`). Users toggle features in
  `~/.config/<server>/settings.json`; enabled features determine the OAuth
  scopes requested at auth time. Disabling a feature hides its tools from
  Claude the next session — no code change.
- **Decorator-based tool registry** (`tools/_registry.py` + `@tool(...)` on
  each handler). Schema and implementation live side-by-side. `tools/__init__.py`
  is a 20-line index, not a 300-line registry.
- **Structured errors** (`tools/_errors.py`). Every handler-level failure
  returns `{ok: False, error, retryable}` via the `error()` helper. A regex
  guard in the test suite prevents regressions to ad-hoc error dicts.
- **Rate limiting + retry at the single API choke point** (`auth.with_retry`).
  Token-bucket limiter (default 5 req/sec sustained, burst 10) with 429/5xx
  backoff and `Retry-After` respect. Every tool that hits Google funnels
  through this one function.
- **Soft delete instead of real delete.** Destructive operations move items to
  a well-known `_delete-later` (Drive) or equivalent location. The user
  reviews and empties in batches via the native UI. No tool ever calls a
  terminal `.delete()` endpoint.
- **Tests hit MagicMock service chains, not real APIs.** The Google client is
  a fluent builder (`svc.files().list(...).execute()`); unit tests stub the
  chain and assert request *shape* (the query sent, the body, the parameters).
  No credentials needed to run the suite.
- **Tokens and config isolated per server.** `~/.config/<server>/` holds
  `settings.json`, `oauth-client.json`, `tokens.json`, and `backups/`. Never
  share credential files across servers.

## Starting a new MCP server in this workspace

1. `mkdir <name>/` alongside `gspace/`.
2. `cd <name> && python3 -m venv .venv && source .venv/bin/activate`.
3. Bootstrap `pyproject.toml` with `[project.scripts]` pointing at a `serve`
   command.
4. Copy the conventions modules from `gspace/gspace/`: `_errors.py`,
   `_registry.py`, `auth.py` (adapt for whichever service you're wrapping).
5. Add entry to the "Active servers" table above.
6. Register with Claude Code: `cd ~ && claude mcp add <name> <absolute-path-to-serve-binary>`.

## Resources

- [gspace/CLAUDE.md](gspace/CLAUDE.md) — full spec for the Google Workspace server
- Claude Code MCP docs: https://docs.claude.com/en/docs/claude-code
