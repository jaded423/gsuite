# In-house MCP workspace

This directory hosts one or more in-house Model Context Protocol (MCP) servers
that we build and maintain ourselves. Each server lives in its own subdirectory
with its own Python package, virtualenv, tests, and CLAUDE.md. Shared
conventions (patterns every server should follow) live here.

## Active servers

| Server | Subdir | Purpose | Status |
|---|---|---|---|
| `gspace` | [gspace/](gspace/CLAUDE.md) | Google Workspace — Gmail, Drive, Docs, Sheets, Slides, Calendar | 38 tools, 101 tests. Retired `mcp-elevated` on 2026-04-17. |

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
