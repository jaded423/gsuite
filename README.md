<div align="center">

```
 ██████╗ ███████╗██████╗  █████╗  ██████╗███████╗
██╔════╝ ██╔════╝██╔══██╗██╔══██╗██╔════╝██╔════╝
██║  ███╗███████╗██████╔╝███████║██║     █████╗
██║   ██║╚════██║██╔═══╝ ██╔══██║██║     ██╔══╝
╚██████╔╝███████║██║     ██║  ██║╚██████╗███████╗
 ╚═════╝ ╚══════╝╚═╝     ╚═╝  ╚═╝ ╚═════╝╚══════╝
```

# 🐍 gspace

**In-house Google Workspace MCP · 38 tools · 101 tests · Gmail, Drive, Docs, Sheets, Slides, Calendar**

[jadedviber.com](https://jadedviber.com) · [/now](https://jadedviber.com/now.html) · [github.com/jaded423](https://github.com/jaded423)

*One MCP. All of Workspace. Built because the existing ones hit ceilings.*

![Python](https://img.shields.io/badge/python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![MCP](https://img.shields.io/badge/Model_Context_Protocol-purple?style=for-the-badge)
![Tests](https://img.shields.io/badge/tests-101_passing-brightgreen?style=for-the-badge)
![License](https://img.shields.io/badge/license-MIT-bd93f9?style=for-the-badge)

</div>

---

```bash
$ whoami
joshua brown — vibe coder · homelab tinkerer · AI-driven dev

$ cat /why.md
the public Workspace MCPs cover the basics. they break on:
- list_filters returning empty when scope IS granted
- no bulk-reclassify (filters only catch NEW mail)
- no declarative rule model with exception semantics
- no LLM-assisted classification
- no backup/restore — filter edits are destructive
- two OAuth clients, half-coverage each

gspace fixes all of those.

$ ls gspace/tools/
gmail/  drive/  docs/  sheets/  slides/  calendar/  rules/
```

---

## ✨ What's inside

- 📬 **Full Gmail control** — filters (list/create/replace/backup/restore), bulk reclassify of existing mail, LLM-assisted classification, declarative rule engine with `if/else` and `except_in` semantics
- 📁 **Drive ops** — search, read, move, soft-delete (moves to `_delete-later`, never hits the terminal `.delete()` endpoint)
- 📄 **Docs / Sheets / Slides** — content read, structured edits, batch updates
- 📆 **Calendar** — list, create, update events; respects busy windows
- 🔐 **One OAuth client, scope-on-demand** — features map to scopes in `settings.py`; toggling a feature changes which scopes get requested at auth time
- 🧠 **LLM classification** — uses Anthropic API (Claude) to label messages by body content, not just metadata
- 🛡️ **Soft-delete everywhere** — destructive ops move to recoverable locations. Manual empty via native UI
- ⚡ **Rate limiter at the choke point** — token-bucket (default 5 req/s, burst 10) with 429/5xx backoff and `Retry-After` respect. Every Google API call funnels through one function
- 🧪 **Tests hit MagicMock service chains, not real APIs** — no credentials needed to run the suite

---

## 🏗️ Architecture highlights

**Decorator-based tool registry.** Each handler in `gspace/tools/<area>.py` carries `@tool(name="...", schema=...)`. `tools/__init__.py` is a 20-line index, not a 300-line registry.

**Feature flags + scope mapping.** `~/.config/gspace/settings.json` lists enabled features. `gspace serve` reads it, computes the union of required OAuth scopes, and only exposes the tools whose features are on. Disabling a feature hides its tools from Claude on next session — no code change needed.

**Structured errors at every boundary.** Every handler-level failure returns `{ok: False, error, retryable}` via `tools/_errors.py:error()`. A regex guard in the test suite prevents regressions to ad-hoc error dicts.

**Declarative rule engine with `except_in`.** Gmail filters can't reference each other, so coordinated routing (e.g. "vendor X goes to CS, EXCEPT 'Thank you' subjects which go to Billing") normally takes 3+ scattered filters with hand-tuned `negatedQuery` strings. The rule compiler in `gspace/rules/engine.py` takes one YAML rule with `if/else` semantics and emits the right filter set. See [`rules/example-routing.yaml`](rules/example-routing.yaml).

**Soft-delete, not delete.** Destructive ops move items to `_delete-later/` (Drive) or equivalent labels (Gmail). No tool ever calls a terminal `.delete()` endpoint. Recovery is one drag away.

---

## 🚀 Install

```bash
# Clone
git clone https://github.com/jaded423/gspace.git ~/projects/gspace
cd ~/projects/gspace/gspace

# Install
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Set up OAuth (one-time)
# 1. Create a GCP project + enable Gmail/Drive/Docs/Sheets/Slides/Calendar APIs
# 2. Create an OAuth 2.0 Desktop client
# 3. Download credentials → ~/.config/gspace/oauth-client.json
gspace auth   # opens browser, completes flow, caches refresh token

# Configure features
gspace settings  # interactive — pick which feature groups to enable
```

**Wire into Claude Desktop** (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "gspace": {
      "command": "/Users/you/projects/gspace/gspace/.venv/bin/python",
      "args": ["-m", "gspace.server"]
    }
  }
}
```

Restart Claude Desktop — `gspace` tools now available.

---

## 📦 Tool surface

<details>
<summary><b>Gmail (12 tools)</b></summary>

| Tool | Purpose |
|---|---|
| `gmail_search_threads` | Query search |
| `gmail_get_thread` | Full thread incl. body |
| `gmail_list_labels` | All labels |
| `gmail_create_label` / `update_label` / `delete_label` | Label CRUD |
| `gmail_label_message` / `unlabel_message` | Bulk label ops |
| `gmail_list_filters` | All filters (works where `@gongrzhe` breaks) |
| `gmail_create_filter` / `delete_filter` | Filter CRUD |
| `gmail_create_filter_from_template` | DSL → filter compiler |
| `gmail_apply_rules` | YAML ruleset → coordinated filter set |
| `gmail_classify_message` | LLM-assisted category by body |

</details>

<details>
<summary><b>Drive (10 tools)</b></summary>

| Tool | Purpose |
|---|---|
| `drive_search_files` / `list_recent_files` | Query + recents |
| `drive_get_file_metadata` / `get_file_permissions` | Metadata + ACL |
| `drive_read_file_content` / `download_file_content` | Content fetch |
| `drive_create_file` / `copy_file` | Create + duplicate |
| `drive_soft_delete` | Move to `_delete-later/` |
| `drive_share` / `unshare` | Permission management |

</details>

<details>
<summary><b>Docs / Sheets / Slides / Calendar (16 tools)</b></summary>

| Area | Tools |
|---|---|
| Docs | content read, structured edits, batch updates |
| Sheets | range read/write, formula application |
| Slides | slide content, layout updates |
| Calendar | list/create/update events, busy-window respect |

Full list: see [`gspace/tools/`](gspace/gspace/tools/) — each module declares its surface via `@tool(...)`.

</details>

---

## 🧠 Design conventions

These patterns came out of building gspace and are worth carrying forward to any MCP:

1. **Feature flags + scope mapping** — users toggle features in settings, enabled features determine OAuth scopes. No code change to disable a tool group.
2. **Decorator-based tool registry** — schema + implementation co-located. No 300-line registry file.
3. **Structured errors everywhere** — `{ok, error, retryable}` shape, guarded by regex test.
4. **Rate-limit + retry at the single API choke point** — every Google call funnels through `auth.with_retry`.
5. **Soft-delete, not delete** — moves to `_delete-later`, user reviews + empties via native UI.
6. **Tests hit MagicMock chains** — `svc.files().list(...).execute()` is fluent; tests stub the chain and assert request *shape*. No credentials needed.
7. **Tokens isolated per server** — `~/.config/<server>/` holds OAuth client + refresh token + settings. Cross-server scope leak impossible.

See [`CLAUDE.md`](CLAUDE.md) + [`gspace/CLAUDE.md`](gspace/CLAUDE.md) for the full architecture writeup.

---

## 🧪 Tests

```bash
cd gspace
.venv/bin/python -m pytest -q
# 101 passed
```

No credentials required. Tests mock the Google service builder chain end-to-end.

---

## 📁 Structure

```
mcp/                              # workspace — can host multiple MCPs
├── CLAUDE.md                     # workspace overview + cross-MCP conventions
├── README.md                     # this file
└── gspace/                       # the Workspace MCP
    ├── pyproject.toml
    ├── CLAUDE.md                 # gspace internals (architecture, decisions)
    ├── gspace/
    │   ├── server.py             # MCP server (stdio transport)
    │   ├── auth.py               # OAuth + token refresh + rate limiter
    │   ├── settings.py           # Feature flags + scope mapping
    │   ├── cli.py                # `gspace auth`, `gspace settings`, etc.
    │   ├── tools/                # @tool-decorated handlers per area
    │   └── rules/
    │       └── engine.py         # Declarative rule compiler
    ├── rules/
    │   └── example-routing.yaml  # Schema demo
    ├── tests/                    # MagicMock chain tests
    └── docs/changelog.md
```

---

## 🤖 AI-assisted, end-to-end

Built through iterative dialogue with Claude (Anthropic), shipped over ~3 weeks. Architecture decisions, error shapes, the rule DSL, even the test patterns — all came out of conversation, then tested in phases.

Same approach behind [`nvimConfig`](https://github.com/jaded423/nvimConfig), [`terminalConfig`](https://github.com/jaded423/terminalConfig), and the rest of the stack at [jadedviber.com](https://jadedviber.com).

---

## 🐛 Troubleshooting

```bash
gspace auth              # re-run OAuth (e.g. after adding a feature → new scope)
gspace settings status   # which features are enabled, which scopes are granted
gspace settings missing  # list scopes required but not yet granted
```

**Filter list returns empty?** Verify `gmail.settings.basic` scope is granted — `gspace settings status` will tell you.

**Tools missing from Claude?** Restart Claude Desktop after `gspace settings` changes. Tool registry is computed at server start.

---

## 🔗 Resources

- [Model Context Protocol spec](https://spec.modelcontextprotocol.io/) · [MCP SDK (Python)](https://github.com/modelcontextprotocol/python-sdk)
- [Google Workspace APIs](https://developers.google.com/workspace) · [Gmail filter docs](https://developers.google.com/gmail/api/guides/filter_settings)
- [CLAUDE.md](CLAUDE.md) — workspace + cross-MCP conventions
- [gspace/CLAUDE.md](gspace/CLAUDE.md) — gspace internals (391 lines, full architecture story)

---

## 📝 License

MIT — see [LICENSE](LICENSE)

---

<div align="center">

```
$ gspace serve
[stdio] gspace MCP ready — 38 tools registered
```

*<sub>maintained by [@jaded423](https://github.com/jaded423) · built end-to-end through dialogue with AI · cyberpunk-styled · monospace everything</sub>*

**[jadedviber.com](https://jadedviber.com)** · *All vibe. No grind.* 🐍

</div>
