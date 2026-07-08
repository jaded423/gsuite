"""Gmail label tools — list and create labels.

The bulk/move tools (`gmail_batch_modify`, `gmail_move_label`) act on label
*ids*, but nothing surfaced the id↔name map — you had to already know the id.
`gmail_list_labels` fills that gap; `gmail_create_label` makes a new user label
so a filter/move can target it.

`gmail_list_labels` runs under `gmail.read` (readonly scope covers
`labels.list`). `gmail_create_label` needs write access, so it rides the
already-granted `gmail.modify` scope via the `gmail.bulk_modify` feature — no
new scope, no re-consent.
"""

from __future__ import annotations

from typing import Any

from ..auth import build_service, with_retry
from ._errors import error
from ._registry import tool


def _gmail():
    return build_service("gmail")


def _label_summary(lbl: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": lbl.get("id"),
        "name": lbl.get("name"),
        "type": lbl.get("type"),  # "system" or "user"
    }


@tool(
    name="gmail_list_labels",
    feature="gmail.read",
    description=(
        "List all Gmail labels (id, name, type). Use it to resolve a label "
        "name to the id that `gmail_batch_modify` / `gmail_move_label` need. "
        "Includes system labels (INBOX, UNREAD, STARRED, TRASH, …) and user "
        "labels."
    ),
    input_schema={"type": "object", "properties": {}},
)
def gmail_list_labels() -> dict[str, Any]:
    svc = _gmail()
    resp = with_retry(lambda: svc.users().labels().list(userId="me").execute())
    labels = resp.get("labels", []) or []
    labels.sort(key=lambda l: (l.get("type") != "user", (l.get("name") or "").lower()))
    return {
        "ok": True,
        "count": len(labels),
        "labels": [_label_summary(l) for l in labels],
    }


@tool(
    name="gmail_create_label",
    feature="gmail.bulk_modify",
    description=(
        "Create a new user label. Nest it by using `/` in the name (e.g. "
        "'Clients/Acme'). Returns the new label's id. Errors if a label with "
        "that name already exists."
    ),
    input_schema={
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": {"type": "string", "description": "Label name; `/` nests it"},
            "label_list_visibility": {
                "type": "string",
                "enum": ["labelShow", "labelShowIfUnread", "labelHide"],
                "default": "labelShow",
            },
            "message_list_visibility": {
                "type": "string",
                "enum": ["show", "hide"],
                "default": "show",
            },
        },
    },
)
def gmail_create_label(
    name: str,
    label_list_visibility: str = "labelShow",
    message_list_visibility: str = "show",
) -> dict[str, Any]:
    svc = _gmail()
    body = {
        "name": name,
        "labelListVisibility": label_list_visibility,
        "messageListVisibility": message_list_visibility,
    }
    try:
        lbl = with_retry(
            lambda: svc.users().labels().create(userId="me", body=body).execute()
        )
    except Exception as e:  # noqa: BLE001 — surface Google's 409 as a clean error
        if "409" in str(e) or "already exists" in str(e).lower():
            return error(f"a label named {name!r} already exists")
        raise
    return {"ok": True, **_label_summary(lbl)}
