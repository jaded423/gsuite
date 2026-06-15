"""Google Slides tools — read, create, add slide, replace text.

The intended workflow: build a template deck in the UI with `{{placeholder}}`
strings, then populate it by calling `slides_replace_text` with a dict of
substitutions. This keeps slide layout, fonts, and branding in the template
(where the UI tools are better) and moves the programmatic work to text only.

`slides_add_slide` creates a blank slide at the given position — richer
text-population is out of scope here; use a templated deck + replace_text
when placeholder-based filling isn't enough.
"""

from __future__ import annotations

import logging
from typing import Any

from ..auth import build_service, with_retry
from ._errors import error
from ._registry import tool

log = logging.getLogger("gsuite.tools.slides")

VALID_LAYOUTS = {
    "BLANK",
    "TITLE_AND_BODY",
    "TITLE_ONLY",
    "TITLE",
    "SECTION_HEADER",
    "TITLE_AND_TWO_COLUMNS",
    "ONE_COLUMN_TEXT",
    "MAIN_POINT",
    "BIG_NUMBER",
}


def _svc():
    return build_service("slides")


def _slide_text(slide: dict[str, Any]) -> str:
    """Concatenate all textRun content on a slide in reading order."""
    parts: list[str] = []
    for element in slide.get("pageElements", []) or []:
        shape = element.get("shape") or {}
        text = shape.get("text") or {}
        for te in text.get("textElements", []) or []:
            run = te.get("textRun")
            if run:
                parts.append(run.get("content", ""))
    return "".join(parts).rstrip()


@tool(
    name="slides_read",
    feature="slides.read",
    description=(
        "Read a presentation and return the text content per slide. "
        "Returns `title` and a list of slides with `slide_id` and flattened `text`. "
        "Layout, images, and formatting are not returned."
    ),
    input_schema={
        "type": "object",
        "required": ["presentation_id"],
        "properties": {"presentation_id": {"type": "string"}},
    },
)
def slides_read(presentation_id: str) -> dict[str, Any]:
    svc = _svc()
    deck = with_retry(
        lambda: svc.presentations().get(presentationId=presentation_id).execute()
    )
    slides = [
        {"slide_id": s.get("objectId"), "text": _slide_text(s)}
        for s in deck.get("slides", []) or []
    ]
    return {
        "ok": True,
        "presentation_id": presentation_id,
        "title": deck.get("title"),
        "slide_count": len(slides),
        "slides": slides,
    }


@tool(
    name="slides_create",
    feature="slides.write",
    description="Create a new blank presentation with the given title. Returns ID and URL.",
    input_schema={
        "type": "object",
        "required": ["title"],
        "properties": {"title": {"type": "string"}},
    },
)
def slides_create(title: str) -> dict[str, Any]:
    svc = _svc()
    created = with_retry(
        lambda: svc.presentations().create(body={"title": title}).execute()
    )
    pid = created["presentationId"]
    return {
        "ok": True,
        "presentation_id": pid,
        "title": title,
        "url": f"https://docs.google.com/presentation/d/{pid}/edit",
    }


@tool(
    name="slides_add_slide",
    feature="slides.write",
    description=(
        "Append a slide to a presentation using a predefined layout. Layouts: "
        "BLANK, TITLE_AND_BODY, TITLE_ONLY, SECTION_HEADER, etc. For text "
        "population, build a template deck with placeholders and use "
        "`slides_replace_text`."
    ),
    input_schema={
        "type": "object",
        "required": ["presentation_id"],
        "properties": {
            "presentation_id": {"type": "string"},
            "layout": {
                "type": "string",
                "enum": sorted(VALID_LAYOUTS),
                "default": "TITLE_AND_BODY",
            },
            "insertion_index": {
                "type": "integer",
                "minimum": 0,
                "description": "0-indexed position. Omit to append at the end.",
            },
        },
    },
)
def slides_add_slide(
    presentation_id: str,
    layout: str = "TITLE_AND_BODY",
    insertion_index: int | None = None,
) -> dict[str, Any]:
    if layout not in VALID_LAYOUTS:
        return error(f"invalid layout {layout!r}; must be one of {sorted(VALID_LAYOUTS)}")
    request: dict[str, Any] = {
        "createSlide": {"slideLayoutReference": {"predefinedLayout": layout}}
    }
    if insertion_index is not None:
        request["createSlide"]["insertionIndex"] = insertion_index
    svc = _svc()
    resp = with_retry(
        lambda: svc.presentations()
        .batchUpdate(presentationId=presentation_id, body={"requests": [request]})
        .execute()
    )
    replies = resp.get("replies", []) or []
    slide_id = replies[0].get("createSlide", {}).get("objectId") if replies else None
    return {
        "ok": True,
        "presentation_id": presentation_id,
        "slide_id": slide_id,
        "layout": layout,
    }


@tool(
    name="slides_replace_text",
    feature="slides.write",
    description=(
        "Run a batch of case-sensitive find/replace operations across every "
        "slide. `replacements` is a mapping of find-string → replace-string. "
        "Designed for templated decks with `{{placeholder}}` markers."
    ),
    input_schema={
        "type": "object",
        "required": ["presentation_id", "replacements"],
        "properties": {
            "presentation_id": {"type": "string"},
            "replacements": {"type": "object", "additionalProperties": {"type": "string"}},
        },
    },
)
def slides_replace_text(
    presentation_id: str, replacements: dict[str, str]
) -> dict[str, Any]:
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
        lambda: svc.presentations()
        .batchUpdate(presentationId=presentation_id, body={"requests": requests})
        .execute()
    )
    replies = resp.get("replies", []) or []
    occurrences = sum(
        r.get("replaceAllText", {}).get("occurrencesChanged", 0) or 0 for r in replies
    )
    return {
        "ok": True,
        "presentation_id": presentation_id,
        "replacements": len(requests),
        "occurrences_changed": occurrences,
    }
