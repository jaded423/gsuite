---
type: reference
title: gsuite install guide
tags: [gsuite, install, setup, oauth, guide, trust-ladder]
related: [index, changelog]
---

# Installing gsuite — guide for Claude

This guide is written for Claude (Claude Code in a terminal, or any Claude with shell access) performing the install on a Mac for a new user. If you are Claude: follow the steps in order, verify each before moving on, and ask the user only at the marked decision points.

**Read § 0 first.** It sets the access profile the rest of the guide assumes.

## 0. The access profile — "see everything, draft email, change nothing"

The default profile for a new user is **read-only plus email drafts**. Claude can read Gmail, Drive, Docs, Sheets, Slides, Calendar and Tasks, can write email *drafts* into Gmail's Drafts folder, and **cannot send email or change anything in Google**. The user reviews every draft in Gmail and presses Send themselves. Access is widened later, one feature at a time, as trust builds (§ 9).

Three layers enforce it, and you set all three during the install:

| Layer | Set in | What it does |
|---|---|---|
| **Feature flags** (§ 4) | `~/.config/gsuite/settings.json` | Write features stay OFF, so their tools never exist and Google is never asked for their scopes. |
| **Claude Code permissions** (§ 7) | `~/.claude/settings.json` | Hard-blocks the send tools (Claude cannot call them at all), auto-allows the read tools, and prompts the user for each draft. |
| **House rules** (§ 8) | `~/.claude/CLAUDE.md` | Tells Claude how to behave inside the limits: draft, summarize, never ask to unlock send. |

**One thing to explain to the user up front:** Google has no "drafts only" permission. Writing a draft needs the Gmail *modify* scope, and the consent screen will describe it as "Read, compose, send, and permanently delete all your email." That is the only Gmail scope that allows drafts. The no-send guarantee comes from layer 2 (the tool is blocked in Claude Code) and layer 1 (no bulk-modify or filter tools exist), not from Google. Say this plainly before step 5 so the consent screen is not a surprise.

## 1. Prerequisites

```bash
python3 --version   # need 3.11+
git --version
```

If Python is older than 3.11: `brew install python@3.12` (ask the user before installing Homebrew itself if missing).

## 2. Clone and install

The Python package is at the repo root (`pyproject.toml` lives there):

```bash
mkdir -p ~/projects && cd ~/projects
git clone https://github.com/jaded423/gsuite.git
cd gsuite
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/gsuite --version
```

Do **not** run `install.sh` — that script registers Joshua's three-account layout. A single-account install is the manual path in this guide.

## 3. OAuth client file (comes from Joshua, not the repo)

The repo deliberately does **not** contain `oauth-client.json` — Joshua sends it separately (AirDrop, Drive, etc.). For an **@elevatedtrading.com** account it is the client from the Elevated Workspace's own Google Cloud project (an Internal app, so no test-user registration and no "unverified app" screen). Place it at:

```bash
mkdir -p ~/.config/gsuite
mv ~/Downloads/oauth-client.json ~/.config/gsuite/oauth-client.json
chmod 600 ~/.config/gsuite/oauth-client.json
```

If the account is *not* on the Elevated Workspace, it must be registered as a **test user** on the OAuth app — Joshua does this in Google Cloud Console. Auth failing with "access_denied" or "app not verified" means that registration is missing.

## 4. Set the feature flags (the profile from § 0)

Defaults are Gmail read/send/filters/bulk-modify on and everything else off. Change them to the read-everything, draft-only profile. `features enable` takes one name per call:

```bash
G=.venv/bin/gsuite
$G features disable gmail.filters        # no filter/label rules
$G features disable gmail.bulk_modify    # no mass label/archive/delete
$G features enable  drive.read
$G features enable  docs.read
$G features enable  sheets.read
$G features enable  slides.read
$G features enable  calendar.read
$G features enable  tasks                # tasks is one flag for read+write; the write tools are blocked in § 7
$G features list
```

Leave **`gmail.read`** and **`gmail.send`** ON. `gmail.send` is the flag that provides the draft tools (create / update / delete draft) — sending is blocked in § 7, not here. Leave `gmail.classify` and every `*.write` flag OFF.

**Decision point:** show the user `features list` and confirm this is the profile they want. If they want *less* (for example no Drive), disable it now. If they want *more*, still install this profile first and widen it in § 9 after the first successful session.

## 5. Authorize with Google

```bash
.venv/bin/gsuite auth
```

A browser opens. The user signs into the Google account they want Claude to access and reviews the consent screen — it lists exactly the scopes for the features enabled in step 4. Expect: Gmail "read, compose, send, and permanently delete" (see § 0 for why), read-only Drive / Docs / Sheets / Slides / Calendar, and Tasks. A "Google hasn't verified this app" interstitial appears only on the External test app, not the Elevated Internal app; if it does appear, click **Continue**.

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

**Claude Desktop** (optional; note the send lock in § 7 is a Claude Code feature — on Desktop only layers 1 and 3 apply): edit `~/Library/Application Support/Claude/claude_desktop_config.json` (create `mcpServers` if absent — merge, don't clobber existing servers):

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

## 7. Lock sending in Claude Code (permissions)

Claude Code decides per tool whether to run it silently, ask the user, or refuse. Put this in `~/.claude/settings.json`. If the file exists, **merge** the `permissions` object into it (keep the user's other settings); if not, create it with exactly this content:

```json
{
  "permissions": {
    "allow": [
      "mcp__gsuite__gmail_search_messages",
      "mcp__gsuite__gmail_read_message",
      "mcp__gsuite__gmail_get_thread",
      "mcp__gsuite__gmail_get_attachment",
      "mcp__gsuite__gmail_list_labels",
      "mcp__gsuite__drive_search",
      "mcp__gsuite__drive_list_folder",
      "mcp__gsuite__drive_read_file",
      "mcp__gsuite__drive_get_metadata",
      "mcp__gsuite__drive_list_delete_later",
      "mcp__gsuite__docs_read",
      "mcp__gsuite__sheets_read_range",
      "mcp__gsuite__slides_read",
      "mcp__gsuite__calendar_list_calendars",
      "mcp__gsuite__calendar_list_events",
      "mcp__gsuite__calendar_get_event",
      "mcp__gsuite__tasklists_list",
      "mcp__gsuite__tasks_list"
    ],
    "deny": [
      "mcp__gsuite__gmail_send_message",
      "mcp__gsuite__gmail_send_draft",
      "mcp__gsuite__tasks_create",
      "mcp__gsuite__tasks_update",
      "mcp__gsuite__tasks_delete"
    ]
  }
}
```

What this gives the user:

- **Reads run without a prompt** — otherwise every question would need a click.
- **Drafts prompt every time.** `gmail_create_draft`, `gmail_update_draft` and `gmail_delete_draft` are on neither list, so Claude Code asks before each one and the user sees exactly what is about to be written.
- **Sends are refused outright.** `deny` beats everything; Claude cannot call `gmail_send_message` or `gmail_send_draft` even if asked to.
- **Task edits are refused** for the same reason (the `tasks` flag has no read-only half).

Validate the file and restart Claude Code:

```bash
python3 -m json.tool ~/.claude/settings.json > /dev/null && echo OK
```

## 8. House rules for Claude (behavior inside the limits)

Append this block to `~/.claude/CLAUDE.md` (create the file if missing). It loads into every Claude Code session on this Mac:

```markdown
# Google Workspace (gsuite) — house rules

- You have read access to Gmail, Drive, Docs, Sheets, Slides, Calendar and Tasks. Use it freely to answer questions and summarize.
- Email: you may write DRAFTS only (gmail_create_draft / gmail_update_draft). The user reviews and sends from Gmail. The send tools are blocked — never try them, never ask for them to be unblocked, and never work around the block (no "forward to yourself", no calendar invites as a way to message someone).
- You cannot change anything in Google (labels, filters, files, sheets, events, tasks). If a request needs that, say which feature would have to be enabled and stop; do not improvise.
- Before writing a draft, say in one line who it is to and what it says. After writing it, say it is in Gmail's Drafts folder.
- Drafts are signed with the user's name. Do not add anything the user did not ask for (no CCs, no attachments, no "sent via" lines).
- Read-only means read-only for the world too: do not paste email contents or documents into other tools or services unless the user asks.
```

## 9. Verify — three checks, not one

Open a fresh Claude Code session (`claude` in any directory) and run all three:

1. **Read (should just work):** *"Search my Gmail for the 5 most recent messages and list their subjects."* The gsuite tools appear and real subjects come back.
2. **Draft (should prompt):** *"Draft a reply to the newest one saying I'll get back to them tomorrow."* Claude Code asks for permission before the draft tool runs. Approve it, then confirm the draft is in Gmail's Drafts folder — and that nothing was sent.
3. **Send (must be refused):** *"Now send that draft."* Claude must say the send tools are blocked and stop. If it sends, the `deny` block in § 7 is wrong or the settings file did not load — fix that before the user does anything else.

The install is done when all three behave as described.

## 10. Widening access later (the trust ladder)

Each rung is one small change, then restart Claude Code:

- **Let Claude send, with a prompt each time:** delete the two `gmail_send_*` lines from `deny` in `~/.claude/settings.json`. Claude Code then asks before every send. To stop the prompt later, move them to `allow`.
- **Add a write feature** (for example Sheets): `gsuite features enable sheets.write`, then `gsuite auth` (Google re-consents for the new scope), then restart Claude. New tools prompt by default; add them to `allow` when the user is comfortable.
- **Let Claude manage labels or filters:** `gsuite features enable gmail.bulk_modify` / `gmail.filters`, then `gsuite auth`, restart. No new deny entries are needed.
- **Undo everything:** revoke the app at [myaccount.google.com/permissions](https://myaccount.google.com/permissions). Tokens on disk stop working immediately.

## Multiple accounts (optional)

Each additional Google account gets its own config dir and server entry:

```json
"gsuite-work": {
  "command": "/Users/USERNAME/projects/gsuite/.venv/bin/gsuite",
  "args": ["serve"],
  "env": { "GSUITE_CONFIG_DIR": "/Users/USERNAME/.config/gsuite-work" }
}
```

Run the auth flow per account: `GSUITE_CONFIG_DIR=~/.config/gsuite-work .venv/bin/gsuite auth` (each account also needs its own copy of `oauth-client.json` in its config dir). The § 7 permission entries are per server name, so a second server (`gsuite-work`) needs its own `mcp__gsuite-work__*` lines.

## Troubleshooting

- **"access_denied" / "app not verified" hard block** → the Google account isn't on the Elevated Workspace and isn't a test user yet; ask Joshua to add it in Cloud Console.
- **Tools missing in Claude** → feature disabled, or scope gap (`gsuite status` shows `needs_reauth`); run `gsuite auth`, then restart the Claude app.
- **Scope-gap warning at startup** → a feature was enabled after the last auth; run `gsuite auth` to re-consent.
- **Desktop doesn't see the server** → config JSON syntax error or non-absolute path; validate with `python3 -m json.tool` on the config file.
- **Claude Code prompts for every read** → the `allow` list in § 7 didn't load; check `~/.claude/settings.json` parses and that the server is registered as `gsuite` (the tool prefix must match).
- **Claude sent an email** → the `deny` list didn't load. Fix § 7 first; the flags alone do not block sending.
