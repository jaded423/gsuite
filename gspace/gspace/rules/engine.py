"""Rule engine — YAML ruleset → Gmail filter bodies.

The rule language is declarative so the user writes one cohesive statement per
routing intent instead of 3 loosely-coordinated filters. The compiler handles
the fiddly parts we kept doing by hand in 2026-04-16:

- Boolean fan-in on `from` / `to` / `subject_any_of` (a list compiles to a
  single filter with `OR`-joined criteria, not three filters).
- `if/else` on a condition expands to two filters, the second carrying the
  negated predicate via Gmail's `negatedQuery`.
- `except_in` surfaces as additional `negatedQuery` tokens.
- `actions` like `mark_read`, `archive`, `star` compile to the right
  `add/removeLabelIds` system-label set (Gmail filters can remove INBOX, UNREAD,
  etc. — just not user labels; see learning #1).

Idempotency: a compiled filter's identity is `sha1(criteria + action)`. On
apply we diff the live filter set against the compiled set by hash, create
what's missing, and (only with `prune=True`) delete what no longer appears.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# System-label shortcuts for the `actions:` block in rules.
# Gmail filter actions CAN remove system labels (unlike user labels, see
# learning #1). That's what makes `archive` and `mark_read` expressible as
# pure filter actions with no batchModify chaser.
ACTION_MAP: dict[str, tuple[str, str]] = {
    # name -> (target list, label id)
    "mark_read":   ("removeLabelIds", "UNREAD"),
    "mark_unread": ("addLabelIds", "UNREAD"),
    "archive":     ("removeLabelIds", "INBOX"),
    "star":        ("addLabelIds", "STARRED"),
    "important":   ("addLabelIds", "IMPORTANT"),
    "not_important": ("removeLabelIds", "IMPORTANT"),
    "skip_spam":   ("removeLabelIds", "SPAM"),
    "trash":       ("addLabelIds", "TRASH"),
}


# --- data model --------------------------------------------------------------

@dataclass
class CompiledFilter:
    """A Gmail-API-shaped filter body, plus the rule name that produced it."""

    rule: str
    criteria: dict[str, Any]
    action: dict[str, Any]

    def body(self) -> dict[str, Any]:
        return {"criteria": self.criteria, "action": self.action}

    def key(self) -> str:
        """Stable identity hash for idempotent apply."""
        return hashlib.sha1(
            json.dumps(self.body(), sort_keys=True).encode()
        ).hexdigest()


# --- load --------------------------------------------------------------------

def load_ruleset(path: str | Path) -> dict[str, Any]:
    data = yaml.safe_load(Path(path).read_text())
    if not isinstance(data, dict) or "rules" not in data:
        raise ValueError(f"{path}: expected top-level 'rules:' list")
    return data


# --- helpers -----------------------------------------------------------------

def _or_join(values: list[str]) -> str:
    """Join a list of raw values into a Gmail OR-expression, parenthesized."""
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    return "{" + " ".join(values) + "}"  # Gmail treats {a b c} as OR-group


def _as_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    return [str(v)]


def _apply_label_action(
    action: dict[str, Any], add: list[str], remove: list[str]
) -> None:
    if add:
        action.setdefault("addLabelIds", []).extend(add)
    if remove:
        action.setdefault("removeLabelIds", []).extend(remove)


def _apply_named_actions(action: dict[str, Any], names: list[str]) -> None:
    for n in names:
        if n not in ACTION_MAP:
            raise ValueError(
                f"unknown action {n!r} (known: {sorted(ACTION_MAP)})"
            )
        target, lbl = ACTION_MAP[n]
        action.setdefault(target, []).append(lbl)


# --- compile -----------------------------------------------------------------

def _build_criteria(match: dict[str, Any], extra_negated: list[str]) -> dict[str, Any]:
    """Translate a rule's `match:` block into a Gmail filter criteria dict."""
    c: dict[str, Any] = {}
    if "from" in match:
        c["from"] = _or_join(_as_list(match["from"]))
    if "to" in match:
        c["to"] = _or_join(_as_list(match["to"]))
    if "subject" in match:
        c["subject"] = match["subject"]
    if "subject_any_of" in match:
        # Subject field on filters accepts OR-groups in braces.
        c["subject"] = _or_join(
            [f'"{s}"' for s in _as_list(match["subject_any_of"])]
        )
    if "query" in match:
        c["query"] = match["query"]
    negated = list(extra_negated)
    if "negated_query" in match:
        negated.append(match["negated_query"])
    if negated:
        c["negatedQuery"] = " ".join(f"({n})" for n in negated)
    if match.get("has_attachment"):
        c["hasAttachment"] = True
    if match.get("exclude_chats", True):
        c["excludeChats"] = True
    return c


def _build_action(
    label_name_to_id: dict[str, str],
    to_label: str | list[str] | None,
    remove_labels: list[str] | None,
    named_actions: list[str],
) -> dict[str, Any]:
    action: dict[str, Any] = {}
    add_names = _as_list(to_label)
    add_ids = [label_name_to_id[n] for n in add_names]
    remove_names = _as_list(remove_labels)
    # User labels can't be removed from filters (see learning #1); we surface
    # that at compile time so callers don't discover it as a 400 later.
    for n in remove_names:
        if n in label_name_to_id:
            raise ValueError(
                f"filter actions can't remove the user label {n!r} — "
                "use a batch_modify or move_label op instead"
            )
    _apply_label_action(action, add_ids, [])
    _apply_named_actions(action, named_actions)
    return action


def compile_ruleset(
    ruleset: dict[str, Any], label_name_to_id: dict[str, str]
) -> list[CompiledFilter]:
    """Compile a loaded ruleset into a list of `CompiledFilter` bodies."""
    out: list[CompiledFilter] = []
    rules = ruleset.get("rules", []) or []
    # First pass: index named rules so `except_in: [name]` can reference them.
    by_name: dict[str, dict[str, Any]] = {
        r["name"]: r for r in rules if isinstance(r, dict) and "name" in r
    }

    for rule in rules:
        name = rule.get("name", "<anonymous>")
        match = rule.get("match", {}) or {}

        # except_in: either a label name (→ negate `label:Name`) or another
        # rule name (→ negate that rule's match criteria). List accepted.
        extra_negated: list[str] = []
        for ex in _as_list(rule.get("except_in")):
            if ex in by_name:
                other = by_name[ex].get("match", {}) or {}
                other_query = _match_to_query(other)
                if other_query:
                    extra_negated.append(other_query)
            else:
                extra_negated.append(f"label:{ex}")

        route = rule.get("route")
        actions = _as_list(rule.get("actions"))
        # Actions can also be a dict {mark_read: true, archive: true}
        if isinstance(rule.get("actions"), dict):
            actions = [k for k, v in rule["actions"].items() if v]

        # `route:` shapes:
        #   {to: Billing}                       → one filter
        #   [{if: "...", to: X}, {else: {to: Y}}]  → two filters (the second negates the first)
        if route is None and actions:
            # Actions-only rule (e.g., mark_read of billing receipts).
            crit = _build_criteria(match, extra_negated)
            act = _build_action(label_name_to_id, None, None, actions)
            out.append(CompiledFilter(rule=name, criteria=crit, action=act))
            continue

        if isinstance(route, dict):
            crit = _build_criteria(match, extra_negated)
            act = _build_action(
                label_name_to_id,
                route.get("to"),
                route.get("remove"),
                actions + _as_list(route.get("actions")),
            )
            out.append(CompiledFilter(rule=name, criteria=crit, action=act))
            continue

        if isinstance(route, list):
            negated_so_far: list[str] = []
            for branch in route:
                if "else" in branch:
                    else_clause = branch["else"]
                    crit = _build_criteria(
                        match, extra_negated + negated_so_far
                    )
                    act = _build_action(
                        label_name_to_id,
                        else_clause.get("to"),
                        else_clause.get("remove"),
                        actions + _as_list(else_clause.get("actions")),
                    )
                    out.append(CompiledFilter(rule=name, criteria=crit, action=act))
                    continue
                cond = branch.get("if")
                if cond is None:
                    raise ValueError(
                        f"rule {name!r}: route branch needs `if:` or `else:`"
                    )
                cond_query = _condition_to_query(cond)
                crit = _build_criteria(match, extra_negated)
                # Fold the condition into the base query so the filter only fires
                # when the condition holds.
                existing = crit.get("query", "")
                crit["query"] = (
                    f"({existing}) ({cond_query})" if existing else cond_query
                )
                act = _build_action(
                    label_name_to_id,
                    branch.get("to"),
                    branch.get("remove"),
                    actions + _as_list(branch.get("actions")),
                )
                out.append(CompiledFilter(rule=name, criteria=crit, action=act))
                # The `else` branch (if any) must negate everything prior.
                negated_so_far.append(cond_query)
            continue

        if route is None and not actions:
            raise ValueError(f"rule {name!r}: no route and no actions")

    return out


def _match_to_query(match: dict[str, Any]) -> str:
    """Render a `match:` block back into a Gmail search string (for `except_in`)."""
    parts: list[str] = []
    if v := match.get("from"):
        parts.append(f"from:({_or_join(_as_list(v))})")
    if v := match.get("to"):
        parts.append(f"to:({_or_join(_as_list(v))})")
    if v := match.get("subject"):
        parts.append(f"subject:{v}")
    if v := match.get("subject_any_of"):
        parts.append(f"subject:{_or_join([chr(34)+s+chr(34) for s in _as_list(v)])}")
    if v := match.get("query"):
        parts.append(f"({v})")
    return " ".join(parts)


def _condition_to_query(cond: str) -> str:
    """Translate a few friendly condition shapes into raw Gmail search syntax.

    Supported: `subject contains 'X'`, `subject is 'X'`, or a bare Gmail query.
    Everything else is passed through verbatim, which is the escape hatch for
    anything the mini-DSL doesn't yet cover.
    """
    s = cond.strip()
    low = s.lower()
    if low.startswith("subject contains "):
        rest = s[len("subject contains "):].strip().strip("'\"")
        return f'subject:"{rest}"'
    if low.startswith("subject is "):
        rest = s[len("subject is "):].strip().strip("'\"")
        return f'subject:"{rest}"'
    return s


# --- diff against live state -------------------------------------------------

@dataclass
class DiffPlan:
    to_create: list[CompiledFilter] = field(default_factory=list)
    already_present: list[CompiledFilter] = field(default_factory=list)
    to_delete: list[dict[str, Any]] = field(default_factory=list)


def diff_plan(
    compiled: list[CompiledFilter], current: list[dict[str, Any]], prune: bool = False
) -> DiffPlan:
    """Diff compiled bodies against live filter state.

    Matching is by body hash — same criteria + action object = same filter.
    Prune deletes anything in `current` whose hash isn't in `compiled` (only
    meaningful when the ruleset is considered authoritative).
    """
    def _key(body: dict[str, Any]) -> str:
        return hashlib.sha1(
            json.dumps(
                {"criteria": body.get("criteria", {}), "action": body.get("action", {})},
                sort_keys=True,
            ).encode()
        ).hexdigest()

    compiled_by_key = {c.key(): c for c in compiled}
    current_by_key = {_key(f): f for f in current}

    plan = DiffPlan()
    for k, c in compiled_by_key.items():
        (plan.already_present if k in current_by_key else plan.to_create).append(c)
    if prune:
        plan.to_delete = [f for k, f in current_by_key.items() if k not in compiled_by_key]
    return plan
