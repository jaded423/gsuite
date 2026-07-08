---
type: reference
title: gsuite install guide
tags: [gsuite, install, setup, oauth, guide]
related: [index, changelog]
---

# Installing gsuite — guide for Claude

This guide is written for Claude (Claude Code in a terminal, or any Claude with shell access) performing the install on a Mac for a new user. If you are Claude: follow the steps in order, verify each before moving on, and ask the user only at the marked decision points.

## What you're installing

`gsuite` is a local MCP server for Google Workspace (Gmail, Drive, Docs, Sheets, Slides, Calendar). The user controls exactly what it can touch in two layers:

1. **Feature flags** — each tool group (e.g. `gmail.read`, `sheets.write`) can be enabled/disabled; disabled groups are invisible to Claude.
2. **Google OAuth scopes** — gsuite requests only the scopes for enabled features, and Google's consent screen shows the user exactly what's being granted before anything is authorized.

Tokens are stored locally in `~/.config/gsuite/tokens.json` and never leave the machine. Access can be revoked any time at [myaccount.google.com/permissions](https://myaccount.google.com/permissions).

## 1. Prerequisites

```bash
python3 --version   # need 3.11+
git --version
```

If Python is older than 3.11: `brew install python@3.12` (ask the user before installing Homebrew itself if missing).

## 2. Clone and install

The Python package lives in the `gsuite/` subdirectory of the repo:

```bash
mkdir -p ~/projects && cd ~/projects
git clone https://github.com/jaded423/gsuite.git
cd gsuite
python3 -m venv .venv
.venv/bin/pip install -e ./gsuite
.venv/bin/gsuite --version
```

## 3. OAuth client file (comes from Joshua, not the repo)

The repo deliberately does **not** contain `oauth-client.json` — Joshua sends it separately (AirDrop, Drive, etc.). Place it at:

```bash
mkdir -p ~/.config/gsuite
mv ~/Downloads/oauth-client.json ~/.config/gsuite/oauth-client.json
```

The user's Google account must also be registered as a **test user** on the OAuth app — Joshua does this in Google Cloud Console. (Cody's account was added 2026-06-12.) If auth later fails with "access_denied" or "app not verified", this registration is the first thing to check.

## 4. Choose features (user decision — walk them through it)

Defaults: Gmail read/send/filters on, everything else off. Show the list and let the user decide what Claude may touch:

```bash
.venv/bin/gsuite features list
.venv/bin/gsuite features enable sheets.read      # examples
.venv/bin/gsuite features enable calendar.read
.venv/bin/gsuite features disable gmail.send
```

Read and write are separate flags per product (`drive.read` vs `drive.write`, etc.) — a read-only setup is a perfectly good starting point. Features can be changed later; newly enabled features may require re-running auth (step 5).

## 5. Authorize with Google

```bash
.venv/bin/gsuite auth
```

A browser opens. The user signs into the Google account they want Claude to access and reviews the consent screen — it lists exactly the scopes for the features enabled in step 4, nothing more. A "Google hasn't verified this app" interstitial is expected (the app is in testing mode): click **Continue**.

Verify:

```bash
.venv/bin/gsuite status   # needs_reauth should be false
```

## 6. Register the MCP server

Use the **absolute** path (`$HOME` won't expand in Desktop's config). Determine it first: `echo "$HOME/projects/gsuite/.venv/bin/gsuite"`.

**Claude Code:**

```bash
claude mcp add --scope user gsuite -- "$HOME/projects/gsuite/.venv/bin/gsuite" serve
```

**Claude Desktop:** edit `~/Library/Application Support/Claude/claude_desktop_config.json` (create `mcpServers` if absent — merge, don't clobber existing servers):

```json
{
  "mcpServers": {
    "gsuite": {
      "command": "/Users/USERNAME/projects/gsuite/.venv/bin/gsuite",
      "args": ["serve"]
    }
  }
}
```

Then fully quit and reopen Claude Desktop (Cmd-Q, not just close the window).

## 7. Verify

In a fresh Claude conversation:

> "Search my Gmail for the 5 most recent messages and list their subjects."

If the gsuite tools appear and the search returns real messages, the install is done.

## Multiple accounts (optional)

Each additional Google account gets its own config dir and server entry:

```json
"gsuite-work": {
  "command": "/Users/USERNAME/projects/gsuite/.venv/bin/gsuite",
  "args": ["serve"],
  "env": { "GSUITE_CONFIG_DIR": "/Users/USERNAME/.config/gsuite-work" }
}
```

Run the auth flow per account: `GSUITE_CONFIG_DIR=~/.config/gsuite-work .venv/bin/gsuite auth` (each account also needs its own copy of `oauth-client.json` in its config dir, and must be a test user on the OAuth app).

## Troubleshooting

- **"access_denied" / "app not verified" hard block** → the Google account isn't a test user yet; ask Joshua to add it in Cloud Console.
- **Tools missing in Claude** → feature disabled, or scope gap (`gsuite status` shows `needs_reauth`); run `gsuite auth`, then restart the Claude app.
- **Scope-gap warning at startup** → a feature was enabled after the last auth; run `gsuite auth` to re-consent.
- **Desktop doesn't see the server** → config JSON syntax error or non-absolute path; validate with `python3 -m json.tool` on the config file.
