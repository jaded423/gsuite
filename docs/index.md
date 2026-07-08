---
type: index
title: gsuite docs — index
tags: [index, catalog, gsuite, google-workspace, mcp]
related: [changelog]
---

# gsuite docs — index

Catalog of the **gsuite** in-house Google Workspace MCP server (Gmail, Drive, Docs, Sheets,
Slides, Calendar, Tasks — 63 tools as of 2026-07-08, see roster note below; 3 per-account
instances). This is a **Tier-2 leaf repo**: one
server, one purpose. It orchestrates nothing, so it has **no `wiki/` tree** (no
`components/`, no `concepts/`) — just its own typed docs, cataloged here. (Contrast: the
[`mcp`](../../mcp/wiki/index.md) meta-repo *is* a hub and gets the full `wiki/` treatment.)

> gsuite's **outward** role — how it fits the MCP fleet — lives in the meta-repo:
> `~/projects/mcp/wiki/components/gsuite.md`. This repo's docs are the **inward** view:
> how gsuite works internally. Two altitudes, one home each; neither restates the other.

> **Tool roster:** the tool registry in code is the single source of truth — there is no
> hand-maintained `TOOLS.md` to drift. For the live list run **`gsuite tools`** (or
> `gsuite tools --json`); it prints every tool grouped by feature. Drift is guarded by
> `tests/test_registry.py::EXPECTED_TOOLS`. Docs cite the count; the command is the list.

## Docs (typed)

| Doc | Type | What |
|---|---|---|
| [../CLAUDE.md](../CLAUDE.md) | reference | **Current-state reference** — live auth model, feature-flag/scope mechanics, multi-org OAuth setup + runbook. Lean; points here for the rest. |
| [design-and-history.md](design-and-history.md) | log | Original design proposal + phase build-log (the "why"), plus the still-authoritative Gmail-filter-engine gotchas. Archived out of CLAUDE.md 2026-07-07. |
| [../INSTALL.md](../INSTALL.md) | reference | Step-by-step install guide (written for Claude doing the install on a new Mac). |
| [changelog.md](changelog.md) | log | Version history — what changed, when. |
| `../TODO.md` | — | Backlog (task-state store, not a wiki doc — kept untyped by convention). |

## Conventions

Frontmatter carries `type` (required), `title`, `tags`, `related`. This repo stays Tier-2
until/unless it ever orchestrates multiple sub-projects — size alone doesn't promote it to a
`wiki/` hub. The former 558-line `CLAUDE.md` (a frozen design proposal) was slimmed 2026-07-07:
current-operational content stayed in `CLAUDE.md`; the proposal + build-log moved to
[design-and-history.md](design-and-history.md). Machine-defined lists (the tool roster) are
never restated in prose — code is the source, `gsuite tools` prints it, a test guards drift.
