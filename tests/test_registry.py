"""Tests for the decorator-based tool registry."""

from __future__ import annotations

from gsuite.tools import all_tools, build_registry


EXPECTED_TOOLS = {
    "gmail.read": {
        "gmail_search_messages",
        "gmail_read_message",
    },
    "gmail.send": {
        "gmail_create_draft",
        "gmail_update_draft",
        "gmail_delete_draft",
        "gmail_send_message",
    },
    "gmail.filters": {
        "gmail_list_filters",
        "gmail_get_filter",
        "gmail_create_filter",
        "gmail_replace_filter",
        "gmail_delete_filter",
        "gmail_backup_filters",
        "gmail_restore_filters",
        "gmail_apply_rules",
        "gmail_export_rules",
    },
    "gmail.bulk_modify": {
        "gmail_batch_modify",
        "gmail_reclassify_filter",
        "gmail_move_label",
    },
    "gmail.classify": {
        "gmail_classify_message",
        "gmail_classify_label",
    },
    "drive.read": {
        "drive_search",
        "drive_list_folder",
        "drive_list_delete_later",
        "drive_get_metadata",
    },
    "drive.write": {
        "drive_create_folder",
        "drive_rename",
        "drive_move",
        "drive_share",
        "drive_soft_delete",
    },
    "docs.read": {"docs_read"},
    "docs.write": {"docs_create", "docs_append_text", "docs_find_replace"},
    "sheets.read": {"sheets_read_range"},
    "sheets.write": {
        "sheets_append_rows",
        "sheets_update_range",
        "sheets_create",
        "sheets_add_sheet",
        "sheets_rename_sheet",
        "sheets_delete_sheet",
    },
    "slides.read": {"slides_read"},
    "slides.write": {"slides_create", "slides_add_slide", "slides_replace_text"},
    "calendar.read": {"calendar_list_events"},
    "calendar.write": {"calendar_create_event", "calendar_update_event"},
}


def test_all_expected_tools_registered():
    registered = {t.name for t in all_tools()}
    expected = {n for names in EXPECTED_TOOLS.values() for n in names}
    assert registered == expected


def test_every_tool_has_correct_feature():
    name_to_feature = {t.name: t.feature for t in all_tools()}
    for feature, names in EXPECTED_TOOLS.items():
        for name in names:
            assert name_to_feature[name] == feature, (
                f"{name} registered under {name_to_feature[name]!r}, expected {feature!r}"
            )


def test_build_registry_respects_feature_flags():
    only_classify = build_registry({"gmail.classify"})
    assert set(only_classify) == EXPECTED_TOOLS["gmail.classify"]


def test_build_registry_empty_when_no_features_enabled():
    assert build_registry(set()) == {}


def test_every_tool_has_valid_schema_shape():
    for t in all_tools():
        assert isinstance(t.input_schema, dict)
        assert t.input_schema.get("type") == "object"
        assert "properties" in t.input_schema
        assert callable(t.handler)
        assert t.description  # non-empty


def test_handler_signatures_match_schema_properties():
    """Every required schema property must be a parameter on the handler.

    This catches renames: if we change a function signature without updating
    the schema (or vice versa), the MCP call would fail with a TypeError at
    runtime. Check it at import time instead.
    """
    import inspect

    for t in all_tools():
        sig = inspect.signature(t.handler)
        params = set(sig.parameters)
        required = set(t.input_schema.get("required", []))
        missing = required - params
        assert not missing, f"{t.name}: schema requires {missing} not in handler signature"
