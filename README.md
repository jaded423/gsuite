# gsuite — a Google Workspace MCP server

Give Claude (or any [MCP](https://modelcontextprotocol.io) client) safe, scoped access to
**Gmail, Drive, Docs, Sheets, Slides, Calendar, and Tasks** — with a settings file that
controls exactly what it's allowed to do.

Point Claude Desktop or Claude Code at `gsuite`, sign in once, and Claude can read and draft
mail, manage Drive files, build docs and sheets, and create calendar events and tasks — using
your Google account, with OAuth consent you approve.

## Highlights

- **One server, the whole Workspace** — Gmail, Drive, Docs, Sheets, Slides, Calendar, Tasks.
- **You control the blast radius.** A `settings.json` of feature flags decides which tools
  Claude even sees, and the server requests **only** the OAuth scopes those features need.
  Turn off `gmail.send` and every send tool simply doesn't exist that session.
- **No console trips after setup.** Change a flag, run `gsuite auth`, approve the new scope
  list in the browser — done. The consent screen is the confirmation step.
- **Multiple accounts** — run one instance per Google account via `GSUITE_CONFIG_DIR`.
- **Local-only credentials.** Your token stays on your machine (`~/.config/gsuite/tokens.json`,
  mode `600`); nothing is uploaded.

## Install

Requires Python 3.11+.

```bash
git clone https://github.com/jaded423/gsuite.git
cd gsuite
./install.sh          # creates a venv, installs the package, registers the MCP
```

## Set up access

1. **Create a Google OAuth client.** In the [Google Cloud Console](https://console.cloud.google.com):
   enable the APIs you want (Gmail, Drive, Docs, Sheets, Slides, Calendar, Tasks), create an
   OAuth **Desktop** client, and download the JSON to `~/.config/gsuite/oauth-client.json`.
2. **Choose what's enabled** in `~/.config/gsuite/settings.json` (see below).
3. **Sign in:**
   ```bash
   gsuite auth
   ```
   A browser opens; approve the scopes. Your token is cached locally.

## Use it

Register the server with your MCP client — Claude Desktop's `claude_desktop_config.json`, or
`claude mcp add` for Claude Code:

```json
{
  "mcpServers": {
    "gsuite": { "command": "/path/to/gsuite/.venv/bin/gsuite", "args": ["serve"] }
  }
}
```

Then just ask: *"Draft a reply to the latest email from Sam,"* *"add a 2 pm Thursday event
called Pricing Review,"* *"make a sheet of this quarter's numbers."*

See the live tool list any time with `gsuite tools` (or `gsuite tools --json`) — the code
registry is the source of truth.

## Controlling features & scopes

Each feature maps to the minimal OAuth scopes it needs. Enable only what you want:

```json
{
  "features": {
    "gmail.read": true,
    "gmail.send": false,
    "drive.read": true,
    "drive.write": false,
    "calendar.write": true,
    "tasks": true
  }
}
```

- **CLI:** `gsuite features enable calendar.write` · `gsuite features disable gmail.send`
- **From Claude:** *"turn on Gmail sending"* — Claude edits the settings and asks you to re-auth.

Either way, **nothing changes without re-auth** — Google shows you the exact new scope list and
you click Allow. The server can *request* scopes but can never self-elevate.

## Multiple Google accounts

Run a separate instance per account by pointing `GSUITE_CONFIG_DIR` at its own config dir:

```bash
GSUITE_CONFIG_DIR=~/.config/gsuite-work     gsuite auth
GSUITE_CONFIG_DIR=~/.config/gsuite-personal gsuite auth
```

Register each as its own MCP server (`gsuite-work`, `gsuite-personal`, …) with the matching
`GSUITE_CONFIG_DIR` in its `env`.

## Notes

- **Revoke access** any time at <https://myaccount.google.com/permissions> — independent of
  this tool.
- **Classification tools** (smart Gmail labeling) call the Anthropic API and need
  `ANTHROPIC_API_KEY` in the environment; every other tool works without it.
- **Tokens on a Testing-mode OAuth app** expire after ~7 days of non-use — just run
  `gsuite auth` again. Apps published to Production (or Internal to a Workspace org) don't.

## Development

Server code is in `gsuite/`; tests in `tests/` (`pytest`). Design notes, the OAuth model, and
version history live in [`docs/`](docs/).
