"""Tool entry points for the rule engine.

`apply_rules`: load a YAML ruleset, compile it to Gmail filter bodies, diff
against the live account, and — only when explicitly confirmed — create,
delete, and optionally reclassify existing mail to match.

`export_rules`: reverse-engineer a starter YAML from the current filter set.
This is lossy (no semantic grouping, no `route: if/else` detection) but gets
you past the blank page.

Every destructive path takes a pre-change backup via gmail_filters.backup_filters
first.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from ..auth import build_service, with_retry
from ..rules.engine import (
    CompiledFilter,
    compile_ruleset,
    diff_plan,
    load_ruleset,
)
from . import gmail_bulk as bulk
from . import gmail_filters as gf
from ._errors import error
from ._registry import tool

log = logging.getLogger("gsuite.tools.gmail_rules")


def _gmail():
    return build_service("gmail")


def _current_filters() -> list[dict[str, Any]]:
    svc = _gmail()
    resp = with_retry(
        lambda: svc.users().settings().filters().list(userId="me").execute()
    )
    return resp.get("filter", []) or []


def _render_compiled(cf: CompiledFilter) -> dict[str, Any]:
    return {"rule": cf.rule, "key": cf.key(), **cf.body()}


@tool(
    name="gmail_apply_rules",
    feature="gmail.filters",
    description=(
        "Compile a YAML ruleset and sync Gmail filters to match. Modes: "
        "`dry-run` (default, reports diff), `create` (create missing). "
        "`prune=true` deletes live filters not in the ruleset. "
        "`reclassify=true` also applies each new filter to existing mail."
    ),
    input_schema={
        "type": "object",
        "required": ["path"],
        "properties": {
            "path": {"type": "string"},
            "mode": {"type": "string", "enum": ["dry-run", "create"], "default": "dry-run"},
            "prune": {"type": "boolean", "default": False},
            "reclassify": {"type": "boolean", "default": False},
            "confirm": {"type": "boolean", "default": False},
        },
    },
)
def apply_rules(
    path: str,
    mode: str = "dry-run",
    prune: bool = False,
    reclassify: bool = False,
    confirm: bool = False,
) -> dict[str, Any]:
    """Compile a ruleset and sync filters to match.

    Modes:
      `dry-run` — show the diff, change nothing (default)
      `create`  — create any filters in the ruleset that aren't live yet

    `prune=True` additionally deletes live filters that aren't in the ruleset.
    Use only when the YAML is the authoritative spec; otherwise you'll wipe
    filters created by hand or another tool.

    `reclassify=True` runs `reclassify_filter` on each newly-created filter so
    existing mail that matches gets the new labels — closing the "filters only
    apply to new mail" gap in one call.

    `confirm=True` is required for any non-dry-run mode.
    """
    src = Path(path)
    if not src.exists():
        return error(f"ruleset not found: {path}")
    ruleset = load_ruleset(src)

    by_name, _ = bulk._label_index()
    # Validate target labels up front — better to fail before mutating anything
    # than halfway through a batch.
    missing_labels: list[str] = []
    for rule in ruleset.get("rules", []) or []:
        for route_block in _iter_targets(rule):
            for t in _as_list(route_block.get("to")):
                if t not in by_name:
                    missing_labels.append(t)
    if missing_labels:
        return error(
            f"unknown target labels: {sorted(set(missing_labels))}. Create them first.",
            missing_labels=sorted(set(missing_labels)),
        )

    compiled = compile_ruleset(ruleset, by_name)
    current = _current_filters()
    plan = diff_plan(compiled, current, prune=prune)

    summary = {
        "mode": mode,
        "prune": prune,
        "reclassify": reclassify,
        "compiled": len(compiled),
        "current": len(current),
        "to_create": [_render_compiled(c) for c in plan.to_create],
        "already_present": [_render_compiled(c) for c in plan.already_present],
        "to_delete": [
            {"id": f.get("id"), "criteria": f.get("criteria"), "action": f.get("action")}
            for f in plan.to_delete
        ],
    }

    if mode == "dry-run":
        return {"ok": True, **summary}
    if mode != "create":
        return error(f"unknown mode: {mode!r}")
    if not confirm:
        return error("confirm=True required for non-dry-run modes", **summary)

    backup = gf.backup_filters(None)["path"]
    svc = _gmail()

    created: list[dict[str, Any]] = []
    for cf in plan.to_create:
        new = with_retry(
            lambda body=cf.body(): svc.users()
            .settings()
            .filters()
            .create(userId="me", body=body)
            .execute()
        )
        created.append({"rule": cf.rule, "id": new.get("id")})

    deleted: list[str] = []
    for f in plan.to_delete:
        with_retry(
            lambda fid=f["id"]: svc.users()
            .settings()
            .filters()
            .delete(userId="me", id=fid)
            .execute()
        )
        deleted.append(f["id"])

    reclassified: list[dict[str, Any]] = []
    if reclassify:
        for entry in created:
            if not entry["id"]:
                continue
            r = bulk.reclassify_filter(entry["id"], dry_run=False)
            reclassified.append({"rule": entry["rule"], "result": r})

    return {
        "ok": True,
        **summary,
        "created": created,
        "deleted": deleted,
        "reclassified": reclassified,
        "backup": backup,
    }


def _iter_targets(rule: dict[str, Any]):
    """Yield every block within a rule that may carry a `to:` target."""
    route = rule.get("route")
    if isinstance(route, dict):
        yield route
    elif isinstance(route, list):
        for b in route:
            if isinstance(b, dict):
                if "else" in b and isinstance(b["else"], dict):
                    yield b["else"]
                else:
                    yield b


def _as_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    return [str(v)]


# --- export ------------------------------------------------------------------

@tool(
    name="gmail_export_rules",
    feature="gmail.filters",
    description=(
        "Export the live filter set as a YAML ruleset. Lossy — one rule per "
        "filter, no if/else detection. Intended as a starter draft."
    ),
    input_schema={
        "type": "object",
        "required": ["path"],
        "properties": {"path": {"type": "string"}},
    },
)
def export_rules(path: str) -> dict[str, Any]:
    """Dump the live filter set as a YAML ruleset.

    Produces one rule per live filter, with a generated name. Criteria are
    translated field-by-field; `if/else` routing is NOT detected — pairs of
    filters that share everything except a negatedQuery will appear as two
    independent rules (manual refactoring pass recommended).
    """
    current = _current_filters()
    _, id_to_name = bulk._label_index()

    rules: list[dict[str, Any]] = []
    for i, f in enumerate(current, start=1):
        crit = f.get("criteria", {}) or {}
        act = f.get("action", {}) or {}
        match: dict[str, Any] = {}
        if "from" in crit:
            match["from"] = crit["from"]
        if "to" in crit:
            match["to"] = crit["to"]
        if "subject" in crit:
            match["subject"] = crit["subject"]
        if "query" in crit:
            match["query"] = crit["query"]
        if "negatedQuery" in crit:
            match["negated_query"] = crit["negatedQuery"]
        if crit.get("hasAttachment"):
            match["has_attachment"] = True

        add_names = [id_to_name.get(lid, lid) for lid in act.get("addLabelIds", []) or []]
        remove_ids = act.get("removeLabelIds", []) or []

        rule: dict[str, Any] = {"name": f"imported-{i:02d}", "match": match}
        # System-label removes become `actions:`; user-label adds become `route.to:`.
        user_adds = [n for n in add_names if n and not n.startswith("CATEGORY_")]
        system_adds_from_ids = [
            lid for lid in act.get("addLabelIds", []) or [] if lid in bulk.SYSTEM_LABELS
        ]
        actions: list[str] = []
        for lid in remove_ids:
            if lid == "UNREAD":
                actions.append("mark_read")
            elif lid == "INBOX":
                actions.append("archive")
            elif lid == "SPAM":
                actions.append("skip_spam")
        if "STARRED" in system_adds_from_ids:
            actions.append("star")
        if "IMPORTANT" in system_adds_from_ids:
            actions.append("important")

        if user_adds:
            rule["route"] = {"to": user_adds[0] if len(user_adds) == 1 else user_adds}
        if actions:
            rule["actions"] = actions
        rules.append(rule)

    payload = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "source": "live filter set",
        "rules": rules,
    }
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(payload, sort_keys=False, width=120))
    return {"ok": True, "path": str(out), "count": len(rules)}
