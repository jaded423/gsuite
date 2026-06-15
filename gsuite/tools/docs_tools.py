"""Google Docs tools — read, create, append text, find/replace.

Minimal v1: text-first operations. Formatting, styles, tables, images, comments
are out of scope until a real workflow needs them. The four tools here cover
the SOP-adjacent workflows: pull a doc's text for summarization, create new
docs programmatically, append to a running log, and run template find/replace
(e.g. `{{date}}` → today's date across a boilerplate doc).
"""

from __future__ import annotations

import logging
from typing import Any

from ..auth import build_service, with_retry
from ._errors import error
from ._registry import tool

log = logging.getLogger("gsuite.tools.docs")


def _svc():
    return build_service("docs")


def _extract_text(doc: dict[str, Any]) -> str:
    """Walk a Docs `content` tree and return a flat string.

    Paragraph elements contain `textRun.content` fragments; joining them yields
    the user-visible text (with newlines embedded where the doc has them).
    """
    parts: list[str] = []
    for block in doc.get("body", {}).get("content", []) or []:
        paragraph = block.get("paragraph")
        if not paragraph:
            continue
        for element in paragraph.get("elements", []) or []:
            run = element.get("textRun")
            if run:
                parts.append(run.get("content", ""))
    return "".join(parts)


@tool(
    name="docs_read",
    feature="docs.read",
    description=(
        "Fetch a Google Doc's body as plain text. Returns `title` and `text`. "
        "Formatting, comments, and embedded objects are stripped."
    ),
    input_schema={
        "type": "object",
        "required": ["document_id"],
        "properties": {"document_id": {"type": "string"}},
    },
)
def docs_read(document_id: str) -> dict[str, Any]:
    svc = _svc()
    doc = with_retry(lambda: svc.documents().get(documentId=document_id).execute())
    return {
        "ok": True,
        "document_id": document_id,
        "title": doc.get("title"),
        "text": _extract_text(doc),
    }


@tool(
    name="docs_create",
    feature="docs.write",
    description=(
        "Create a new Google Doc with the given title. Optional `text` is "
        "inserted as the body. Returns the new document's ID and URL."
    ),
    input_schema={
        "type": "object",
        "required": ["title"],
        "properties": {
            "title": {"type": "string"},
            "text": {"type": "string"},
        },
    },
)
def docs_create(title: str, text: str | None = None) -> dict[str, Any]:
    svc = _svc()
    created = with_retry(lambda: svc.documents().create(body={"title": title}).execute())
    doc_id = created["documentId"]
    if text:
        with_retry(
            lambda: svc.documents()
            .batchUpdate(
                documentId=doc_id,
                body={"requests": [{"insertText": {"location": {"index": 1}, "text": text}}]},
            )
            .execute()
        )
    return {
        "ok": True,
        "document_id": doc_id,
        "title": title,
        "url": f"https://docs.google.com/document/d/{doc_id}/edit",
    }


@tool(
    name="docs_append_text",
    feature="docs.write",
    description=(
        "Append text to the end of a Google Doc. Adds a leading newline so "
        "successive appends don't run together."
    ),
    input_schema={
        "type": "object",
        "required": ["document_id", "text"],
        "properties": {
            "document_id": {"type": "string"},
            "text": {"type": "string"},
        },
    },
)
def docs_append_text(document_id: str, text: str) -> dict[str, Any]:
    if not text:
        return error("text is required")
    svc = _svc()
    resp = with_retry(
        lambda: svc.documents()
        .batchUpdate(
            documentId=document_id,
            body={"requests": [{"insertText": {"endOfSegmentLocation": {}, "text": "\n" + text}}]},
        )
        .execute()
    )
    return {"ok": True, "document_id": document_id, "replies": resp.get("replies", [])}


@tool(
    name="docs_find_replace",
    feature="docs.write",
    description=(
        "Run a batch of case-sensitive find/replace operations across a doc. "
        "`replacements` is a mapping of find-string → replace-string. Ideal "
        "for templated docs with `{{placeholder}}` markers."
    ),
    input_schema={
        "type": "object",
        "required": ["document_id", "replacements"],
        "properties": {
            "document_id": {"type": "string"},
            "replacements": {"type": "object", "additionalProperties": {"type": "string"}},
        },
    },
)
def docs_find_replace(document_id: str, replacements: dict[str, str]) -> dict[str, Any]:
    if not replacements:
        return error("replacements is required")
    requests = [
        {
            "replaceAllText": {
                "containsText": {"text": find, "matchCase": True},
                "replaceText": repl,
            }
        }
        for find, repl in replacements.items()
    ]
    svc = _svc()
    resp = with_retry(
        lambda: svc.documents()
        .batchUpdate(documentId=document_id, body={"requests": requests})
        .execute()
    )
    replies = resp.get("replies", []) or []
    occurrences = sum(
        r.get("replaceAllText", {}).get("occurrencesChanged", 0) or 0 for r in replies
    )
    return {
        "ok": True,
        "document_id": document_id,
        "replacements": len(requests),
        "occurrences_changed": occurrences,
    }
