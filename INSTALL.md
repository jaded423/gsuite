---
type: reference
title: gsuite install guide
tags: [gsuite, install, setup, oauth, guide, trust-ladder]
related: [index, changelog]
---

# Installing gsuite — guide for Claude

This guide is written for Claude (Claude Code in a terminal, or any Claude with shell access) performing the install on a Mac for a new user. If you are Claude: follow the steps in order, verify each before moving on, and ask the user only at the marked decision points.

**Read § 0 first.** It sets the access profile the rest of the guide assumes.

## 0. The access profile — "see everything, ask before every change, never send"

The default profile for a new user installs the **full toolset** — Gmail, Drive, Docs, Sheets, Slides, Calendar, Tasks, read and write — and puts the user in charge of every change:

- **Reads run silently.** Searching mail, reading a sheet, listing calendar events: no prompt.
- **Every write prompts.** Writing an email draft, appending a row, creating a doc, moving a file, adding an event: Claude Code shows the user exactly which tool is about to run with which arguments, and waits for a yes.
- **Sending email is refused outright.** The user reviews every draft in Gmail and presses Send themselves.

Trust widens later by moving one tool at a time from "prompt" to "silent" (§ 10). That is a one-line edit to a settings file — no re-consent with Google, no reinstall.

Two layers make this work, and you set both:

| Layer | Set in | What it does |
|---|---|---|
| **Feature flags + Google scopes** (§ 4–5) | `~/.config/gsuite/settings.json` | Everything enabled. Google grants full read/write scopes once, so the tools exist and never need re-auth as trust grows. |
| **Claude Code permissions** (§ 7) | `~/.claude/settings.json` | The actual gate: read tools auto-allowed, write tools prompt (the default for anything unlisted), the two send tools hard-denied. |

Plus a house-rules block (§ 8) that tells Claude how to behave inside the gate.

**Explain this to the user before the consent screen (§ 5):** Google will show full read/write access for every product, including "Read, compose, send, and permanently delete all your email." That is what makes the tools exist. The *gate* is Claude Code: nothing changes in Google without a prompt they approve, and sending is blocked at the tool level. If the user would rather a product be locked out entirely rather than prompted, § 4 shows how — but the default is "on and gated."

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

## 4. Enable every feature

Defaults are Gmail on and everything else off — that is how an earlier install ended up Gmail-only. Turn the rest on. `features enable` takes one name per call:

```bash
G=.venv/bin/gsuite
for f in drive.read drive.write docs.read docs.write sheets.read sheets.write \
         slides.read slides.write calendar.read calendar.write tasks; do
  $G features enable $f
done
$G features list
```

Everything should now read enabled except **`gmail.classify`** — leave that off (it needs an Anthropic API key file that only Joshua's setup has).

**Decision point:** show the user `features list` and confirm. This is the only place a product can be locked out *entirely* (no tools, no scope): `gsuite features disable <name>` for anything they don't want Claude to see at all. The default is everything on, gated in § 7.

## 5. Authorize with Google

```bash
.venv/bin/gsuite auth
```

**The user runs this themselves, not their Claude.** It blocks until the browser consent flow finishes, and Claude Code's shell tool times out after two minutes, which kills the flow mid-consent. Inside Claude Code, type it with the `!` prefix (`! /path/to/.venv/bin/gsuite auth`) so it runs in the user's own terminal. Claude can run the `features` commands in § 4; it should stop before this step and print the full path for the user to type.

A browser opens. The user signs into the Google account they want Claude to access and reviews the consent screen. It will list full read/write access for Gmail, Drive, Docs, Sheets, Slides, Calendar and Tasks — see § 0 for why that is expected and where the real gate is. A "Google hasn't verified this app" interstitial appears only on the External test app, not the Elevated Internal app; if it does appear, click **Continue**.

Verify:

```bash
.venv/bin/gsuite status   # needs_reauth should be false
```

## 6. Register the MCP server

Use the **absolute** path. Determine it first: `echo "$HOME/projects/gsuite/.venv/bin/gsuite"`.

**Claude Code:**

```bash
claude mcp add --scope user gsuite -- "$HOME/projects/gsuite/.venv/bin/gsuite" serve
```

**Claude Desktop — not for this profile.** Desktop has no deny list, so the send lock in § 7 does not exist there; only the house rules would stand between Claude and the send tool. Register it only if the user explicitly accepts that. Config lives in `~/Library/Application Support/Claude/claude_desktop_config.json` (`mcpServers` → `gsuite` → `command` = the absolute path above, `args` = `["serve"]`; merge, don't clobber; Cmd-Q and reopen).

## 7. The gate — Claude Code permissions

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
      "mcp__gsuite__gmail_list_filters",
      "mcp__gsuite__gmail_get_filter",
      "mcp__gsuite__gmail_export_rules",
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
      "mcp__gsuite__gmail_send_draft"
    ]
  }
}
```

What this gives the user:

- **Reads run without a prompt** (the `allow` list = every read-only tool). Otherwise every question would need a click.
- **Everything else prompts.** Any tool on neither list — drafts, sheet writes, doc edits, file moves, calendar events, tasks, labels, filters — makes Claude Code stop and show the exact call before it runs. That is the gate.
- **Sends are refused outright.** `deny` beats everything; Claude cannot call `gmail_send_message` or `gmail_send_draft` even if asked to.

Validate the file and restart Claude Code:

```bash
python3 -m json.tool ~/.claude/settings.json > /dev/null && echo OK
```

## 8. House rules for Claude (behavior inside the gate)

Append this block to `~/.claude/CLAUDE.md` (create the file if missing). It loads into every Claude Code session on this Mac:

```markdown
# Google Workspace (gsuite) — house rules

- You have full access to Gmail, Drive, Docs, Sheets, Slides, Calendar and Tasks. Reads are free; use them to answer questions and summarize.
- Every change prompts the user. Before a write tool runs, say in one line what it will change (which sheet/doc/file/event, what goes in). Never chain several writes without saying what the set is first, and never delete or move things in bulk without listing them.
- Email: you may write DRAFTS (gmail_create_draft / gmail_update_draft). The user reviews and sends from Gmail. The send tools are blocked — never try them, never ask for them to be unblocked, and never work around the block (no "forward to yourself", no calendar invites or shared docs as a way to message someone).
- Before writing a draft, say who it is to and what it says. After writing it, say it is in Gmail's Drafts folder.
- Drafts are signed with the user's name. Do not add anything the user did not ask for (no CCs, no attachments, no "sent via" lines).
- Read-only means read-only for the world too: do not paste email contents or documents into other tools or services unless the user asks.
```

## 9. Verify — three checks, not one

Open a fresh Claude Code session (`claude` in any directory) and run all three:

1. **Read (should just work, no prompt):** *"Search my Gmail for the 5 most recent messages and list their subjects."* The gsuite tools appear and real subjects come back without a permission prompt.
2. **Write (should prompt):** *"Draft a reply to the newest one saying I'll get back to them tomorrow."* Claude Code asks for permission before the draft tool runs. Approve it, then confirm the draft is in Gmail's Drafts folder — and that nothing was sent. Any Sheets/Drive/Calendar write will prompt the same way.
3. **Send (must be refused):** *"Now send that draft."* Claude must say the send tools are blocked and stop. If it sends, the `deny` block in § 7 is wrong or the settings file did not load — fix that before the user does anything else.

The install is done when all three behave as described.

## 10. Widening access later (the trust ladder)

Every rung is an edit to `~/.claude/settings.json`, then restart Claude Code. Google is never involved again — the scopes are already granted.

- **Stop prompting for a tool the user now trusts** (say, appending rows to sheets): add `"mcp__gsuite__sheets_append_rows"` to `allow`. One tool per line; add them as comfort grows.
- **Let Claude send, with a prompt each time:** delete the two `gmail_send_*` lines from `deny`. Claude Code then asks before every send. To stop the prompt later, move them to `allow`.
- **Go the other way — lock a product out entirely:** `gsuite features disable drive.write` (or any flag), restart Claude. The tools vanish; the granted scope sits unused.
- **Undo everything:** revoke the app at [myaccount.google.com/permissions](https://myaccount.google.com/permissions). Tokens on disk stop working immediately.

## Multiple accounts (optional)

Each additional Google account gets its own config dir and server entry:

```bash
claude mcp add --scope user gsuite-work -e GSUITE_CONFIG_DIR="$HOME/.config/gsuite-work" -- "$HOME/projects/gsuite/.venv/bin/gsuite" serve
```

Run the auth flow per account: `GSUITE_CONFIG_DIR=~/.config/gsuite-work .venv/bin/gsuite auth` (each account also needs its own copy of `oauth-client.json` in its config dir). The § 7 permission entries are per server name, so a second server (`gsuite-work`) needs its own `mcp__gsuite-work__*` lines.

## Troubleshooting

- **"access_denied" / "app not verified" hard block** → the Google account isn't on the Elevated Workspace and isn't a test user yet; ask Joshua to add it in Cloud Console.
- **Tools missing in Claude** → feature disabled, or scope gap (`gsuite status` shows `needs_reauth`); run `gsuite auth`, then restart the Claude app.
- **Scope-gap warning at startup** → a feature was enabled after the last auth; run `gsuite auth` to re-consent.
- **Claude Code prompts for every read** → the `allow` list in § 7 didn't load; check `~/.claude/settings.json` parses and that the server is registered as `gsuite` (the tool prefix must match).
- **Claude sent an email** → the `deny` list didn't load. Fix § 7 first; nothing else blocks sending.
- **Desktop doesn't see the server** → config JSON syntax error or non-absolute path; validate with `python3 -m json.tool` on the config file.
