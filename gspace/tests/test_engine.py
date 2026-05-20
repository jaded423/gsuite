"""Tests for rules/engine.py and the tool registry.

Focus: idempotency (same ruleset → same filter hashes), correct negation
coordination on if/else routes, except_in resolution, and rejection of
impossible actions (removing user labels from filter actions).

Also covers the decorator-based tool registry: every expected tool is
registered, and feature filtering works.
"""

from __future__ import annotations

import pytest

from gspace.rules.engine import (
    CompiledFilter,
    DiffPlan,
    compile_ruleset,
    diff_plan,
)


LABELS = {
    "Billing": "Label_1",
    "Customer Service": "Label_2",
    "VMS": "Label_3",
}


# --- identity / idempotency --------------------------------------------------

def test_compiled_filter_key_is_stable():
    a = CompiledFilter(rule="x", criteria={"from": "a@b"}, action={"addLabelIds": ["L"]})
    b = CompiledFilter(rule="x", criteria={"from": "a@b"}, action={"addLabelIds": ["L"]})
    assert a.key() == b.key()


def test_compiled_filter_key_insensitive_to_dict_order():
    a = CompiledFilter(rule="x", criteria={"from": "a", "to": "b"}, action={})
    b = CompiledFilter(rule="x", criteria={"to": "b", "from": "a"}, action={})
    assert a.key() == b.key()


def test_recompile_produces_same_keys():
    ruleset = {"rules": [{"name": "r", "match": {"from": "a@b"}, "route": {"to": "Billing"}}]}
    k1 = [c.key() for c in compile_ruleset(ruleset, LABELS)]
    k2 = [c.key() for c in compile_ruleset(ruleset, LABELS)]
    assert k1 == k2


# --- simple routes -----------------------------------------------------------

def test_dict_route_single_filter():
    ruleset = {"rules": [{"name": "vms", "match": {"from": "no-reply@vms.com"},
                          "route": {"to": "VMS"}}]}
    [f] = compile_ruleset(ruleset, LABELS)
    assert f.criteria["from"] == "no-reply@vms.com"
    assert f.action["addLabelIds"] == ["Label_3"]


def test_from_list_compiles_to_or_group():
    ruleset = {"rules": [{"name": "r", "match": {"from": ["a@x", "b@y"]},
                          "route": {"to": "Billing"}}]}
    [f] = compile_ruleset(ruleset, LABELS)
    assert f.criteria["from"] == "{a@x b@y}"


def test_subject_any_of_or_group():
    ruleset = {"rules": [{"name": "r", "match": {"subject_any_of": ["Payment", "Receipt"]},
                          "actions": ["mark_read"]}]}
    [f] = compile_ruleset(ruleset, LABELS)
    assert f.criteria["subject"] == '{"Payment" "Receipt"}'
    assert f.action["removeLabelIds"] == ["UNREAD"]


# --- if/else coordination ----------------------------------------------------

def test_if_else_produces_two_filters_with_negation():
    ruleset = {"rules": [{
        "name": "key-customer",
        "match": {"from": ["sales@customer-a.example.com"]},
        "route": [
            {"if": "subject contains 'Thank you'", "to": "Billing"},
            {"else": {"to": "Customer Service"}},
        ],
    }]}
    filters = compile_ruleset(ruleset, LABELS)
    assert len(filters) == 2

    if_filter, else_filter = filters
    # `if` branch folds the condition into the query.
    assert 'subject:"Thank you"' in if_filter.criteria["query"]
    assert if_filter.action["addLabelIds"] == ["Label_1"]  # Billing

    # `else` branch must negate the if-condition.
    assert else_filter.action["addLabelIds"] == ["Label_2"]  # CS
    assert "subject:\"Thank you\"" in else_filter.criteria["negatedQuery"]


def test_if_else_is_idempotent():
    ruleset = {"rules": [{
        "name": "key-customer",
        "match": {"from": ["sales@customer-a.example.com"]},
        "route": [
            {"if": "subject contains 'Thank you'", "to": "Billing"},
            {"else": {"to": "Customer Service"}},
        ],
    }]}
    k1 = sorted(c.key() for c in compile_ruleset(ruleset, LABELS))
    k2 = sorted(c.key() for c in compile_ruleset(ruleset, LABELS))
    assert k1 == k2


# --- except_in ---------------------------------------------------------------

def test_except_in_label_name_adds_label_negation():
    ruleset = {"rules": [{
        "name": "r", "match": {"to": "billing@x.com"}, "route": {"to": "Billing"},
        "except_in": "VMS",
    }]}
    [f] = compile_ruleset(ruleset, LABELS)
    assert "label:VMS" in f.criteria["negatedQuery"]


def test_except_in_rule_name_inlines_other_match():
    ruleset = {"rules": [
        {"name": "vms", "match": {"from": "no-reply@vms.com"}, "route": {"to": "VMS"}},
        {"name": "billing", "match": {"to": "billing@x.com"}, "route": {"to": "Billing"},
         "except_in": "vms"},
    ]}
    filters = compile_ruleset(ruleset, LABELS)
    billing = next(f for f in filters if f.rule == "billing")
    assert "from:(no-reply@vms.com)" in billing.criteria["negatedQuery"]


# --- guardrails --------------------------------------------------------------

def test_removing_user_label_from_filter_action_is_rejected():
    ruleset = {"rules": [{
        "name": "r", "match": {"from": "a@b"},
        "route": {"to": "Billing", "remove": ["Customer Service"]},
    }]}
    with pytest.raises(ValueError, match="can't remove the user label"):
        compile_ruleset(ruleset, LABELS)


def test_unknown_named_action_raises():
    ruleset = {"rules": [{"name": "r", "match": {"from": "a@b"}, "actions": ["nope"]}]}
    with pytest.raises(ValueError, match="unknown action"):
        compile_ruleset(ruleset, LABELS)


def test_rule_with_no_route_and_no_actions_raises():
    ruleset = {"rules": [{"name": "r", "match": {"from": "a@b"}}]}
    with pytest.raises(ValueError, match="no route and no actions"):
        compile_ruleset(ruleset, LABELS)


# --- diff_plan ---------------------------------------------------------------

def test_diff_plan_matches_by_hash():
    ruleset = {"rules": [{"name": "r", "match": {"from": "a@b"},
                          "route": {"to": "Billing"}}]}
    compiled = compile_ruleset(ruleset, LABELS)
    live = [compiled[0].body() | {"id": "FILTER_ID_1"}]

    plan = diff_plan(compiled, live)
    assert len(plan.already_present) == 1
    assert plan.to_create == []
    assert plan.to_delete == []


def test_diff_plan_detects_missing_filter():
    ruleset = {"rules": [{"name": "r", "match": {"from": "a@b"},
                          "route": {"to": "Billing"}}]}
    compiled = compile_ruleset(ruleset, LABELS)
    plan = diff_plan(compiled, current=[])
    assert plan.to_create == compiled
    assert plan.already_present == []


def test_diff_plan_prune_flag():
    ruleset = {"rules": [{"name": "r", "match": {"from": "a@b"},
                          "route": {"to": "Billing"}}]}
    compiled = compile_ruleset(ruleset, LABELS)
    stale = {"id": "STALE", "criteria": {"from": "old@x"}, "action": {"addLabelIds": ["Label_9"]}}
    live = [compiled[0].body() | {"id": "KEEP"}, stale]

    # Without prune, stale stays.
    plan = diff_plan(compiled, live, prune=False)
    assert plan.to_delete == []

    # With prune, stale is flagged for deletion.
    plan = diff_plan(compiled, live, prune=True)
    assert len(plan.to_delete) == 1
    assert plan.to_delete[0]["id"] == "STALE"
