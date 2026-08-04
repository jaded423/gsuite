"""LLM-assisted Gmail classification.

Regex-based filters can't tell "Statement from Dallas Janitorial" (statement)
from "Statement of Work for X" (not a statement). These tools read the email
body with Haiku 4.5 and return a category, optionally applying the
corresponding label move to clean up mis-sorts in bulk.

Prompt structure:
  system = <task spec + category list + output schema>    [cached]
  user   = <email subject + from + body>                  [not cached]

The system prompt is identical across every message in a run, so caching it
drops per-request cost substantially when classifying a whole label.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from anthropic import Anthropic

from ..auth import build_service, with_retry
from ..settings import load_settings
from . import gmail_bulk as bulk
from ._errors import error
from ._registry import tool

log = logging.getLogger("gsuite.tools.gmail_classify")

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
# Empirical: emails rarely need more than a few hundred chars of body to
# classify reliably. Truncating saves tokens without hurting accuracy on the
# "statement vs invoice vs receipt" cases we care about.
BODY_CHAR_BUDGET = 4000


def _gmail():
    return build_service("gmail")


KEY_FILE = Path.home() / ".secrets" / "anthropic_api_key"


def _anthropic_client() -> Anthropic:
    """Build a client, preferring the env var but falling back to a key file.

    The file is the intended home. A shell export is inherited by every child
    process in the session, so the key is deliberately not exported globally --
    same reasoning as the Google OAuth tokens, which live in a file under
    ~/.config and are read only by the code that needs them.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and KEY_FILE.is_file():
        api_key = KEY_FILE.read_text().strip()
    if not api_key:
        raise RuntimeError(
            f"No Anthropic API key: set ANTHROPIC_API_KEY or create {KEY_FILE} "
            "(chmod 600). Classification tools need it; other tools don't."
        )
    return Anthropic(api_key=api_key)


# --- body extraction ---------------------------------------------------------

def _walk_parts(payload: dict[str, Any]):
    yield payload
    for part in payload.get("parts", []) or []:
        yield from _walk_parts(part)


def _decode_b64url(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode()).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _strip_html(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<!--.*?-->", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_body(message: dict[str, Any]) -> str:
    """Pick the first text/plain, else text/html-stripped."""
    payload = message.get("payload", {}) or {}
    plain = ""
    html = ""
    for part in _walk_parts(payload):
        mime = (part.get("mimeType") or "").lower()
        body = (part.get("body") or {}).get("data")
        if not body:
            continue
        text = _decode_b64url(body)
        if mime == "text/plain" and not plain:
            plain = text
        elif mime == "text/html" and not html:
            html = text
    return plain or _strip_html(html)


def _header(message: dict[str, Any], name: str) -> str:
    for h in (message.get("payload", {}) or {}).get("headers", []) or []:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


# --- classify ----------------------------------------------------------------

_SYSTEM_TEMPLATE = """You classify email messages into exactly one of the user's categories.

Categories (respond with the exact name, no other value):
{categories}

Output JSON only, matching this schema:
{{"category": "<one of the above>", "confidence": <0.0-1.0>, "reason": "<one short sentence>"}}

Rules:
- Pick the single best-fit category. If none fit, pick the category named
  "other" if present; otherwise pick the closest and mark confidence <= 0.4.
- Confidence 0.9+ means the email is clearly in this category (e.g., it says
  "Invoice" in the subject for an "invoice" category).
- Confidence 0.5-0.8 means likely but some ambiguity.
- Do not invent categories, do not explain the schema, do not wrap in markdown.
"""


def _build_system(categories: list[str]) -> str:
    lines = "\n".join(f"- {c}" for c in categories)
    return _SYSTEM_TEMPLATE.format(categories=lines)


@tool(
    name="gmail_classify_message",
    feature="gmail.classify",
    description=(
        "Classify a single Gmail message into one of the provided categories "
        "using Haiku 4.5. Returns {category, confidence, reason, usage}. "
        "Requires ANTHROPIC_API_KEY."
    ),
    input_schema={
        "type": "object",
        "required": ["id", "categories"],
        "properties": {
            "id": {"type": "string"},
            "categories": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "model": {"type": "string"},
            "max_tokens": {"type": "integer", "default": 256},
        },
    },
)
def classify_message(
    id: str,
    categories: list[str],
    model: str | None = None,
    max_tokens: int = 256,
) -> dict[str, Any]:
    """Classify a single message. Returns {category, confidence, reason, tokens}."""
    if not categories:
        return error("categories is required")
    svc = _gmail()
    msg = with_retry(
        lambda: svc.users().messages().get(userId="me", id=id, format="full").execute()
    )
    subject = _header(msg, "Subject")
    sender = _header(msg, "From")
    body = _extract_body(msg)[:BODY_CHAR_BUDGET]
    user_text = f"Subject: {subject}\nFrom: {sender}\n\n{body}"

    settings = load_settings()
    model_name = model or settings.llm.get("model", DEFAULT_MODEL)

    client = _anthropic_client()
    resp = client.messages.create(
        model=model_name,
        max_tokens=max_tokens,
        system=[
            {
                "type": "text",
                "text": _build_system(categories),
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_text}],
    )
    text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
    parsed = _parse_json(text, categories)

    usage = {
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
        "cache_read_input_tokens": getattr(resp.usage, "cache_read_input_tokens", 0) or 0,
        "cache_creation_input_tokens": getattr(resp.usage, "cache_creation_input_tokens", 0) or 0,
    }
    return {
        "ok": True,
        "id": id,
        "subject": subject,
        "from": sender,
        **parsed,
        "model": model_name,
        "usage": usage,
    }


def _parse_json(text: str, categories: list[str]) -> dict[str, Any]:
    """Best-effort parse of the model's JSON output; never raise to the caller."""
    s = text.strip()
    # Strip accidental fences.
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n?", "", s).rstrip("`").rstrip().rstrip("`").rstrip()
        s = s.rstrip("```").strip()
    try:
        data = json.loads(s)
    except Exception:
        # Last-ditch: find the first {...} block.
        m = re.search(r"\{.*\}", s, re.S)
        if not m:
            return {"category": None, "confidence": 0.0, "reason": f"unparseable: {s[:120]}"}
        try:
            data = json.loads(m.group(0))
        except Exception:
            return {"category": None, "confidence": 0.0, "reason": f"unparseable: {s[:120]}"}
    cat = data.get("category")
    if cat not in categories:
        return {
            "category": None,
            "confidence": 0.0,
            "reason": f"model returned unknown category {cat!r}",
        }
    try:
        conf = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    return {"category": cat, "confidence": conf, "reason": str(data.get("reason", ""))[:300]}


# --- classify_label ----------------------------------------------------------

@tool(
    name="gmail_classify_label",
    feature="gmail.classify",
    description=(
        "Scan every message in a label, classify each, and optionally move "
        "mis-sorted messages. `category_to_label` maps category → target "
        "label. `apply=true` moves messages whose confidence ≥ min_confidence. "
        "`limit` caps messages per call (default 50)."
    ),
    input_schema={
        "type": "object",
        "required": ["label", "categories"],
        "properties": {
            "label": {"type": "string"},
            "categories": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "category_to_label": {"type": "object"},
            "apply": {"type": "boolean", "default": False},
            "limit": {"type": "integer", "default": 50, "minimum": 1},
            "min_confidence": {"type": "number", "default": 0.7, "minimum": 0, "maximum": 1},
            "model": {"type": "string"},
        },
    },
)
def classify_label(
    label: str,
    categories: list[str],
    category_to_label: dict[str, str] | None = None,
    apply: bool = False,
    limit: int | None = 50,
    min_confidence: float = 0.7,
    model: str | None = None,
) -> dict[str, Any]:
    """Scan every message in `label`, classify each, propose reclassification.

    `category_to_label` maps a category name → target label name. If absent or
    a category has no mapping, that category's messages are reported but not
    moved. When `apply=True`, messages whose classification has confidence
    ≥ min_confidence and whose target label differs from `label` get moved via
    batchModify.

    `limit` caps the number of messages classified per call (cost safety).
    """
    category_to_label = category_to_label or {}
    settings = load_settings()
    model_name = model or settings.llm.get("model", DEFAULT_MODEL)

    q = f"label:{label}"
    ids = bulk._search_ids(q, limit=limit)
    if not ids:
        return {"ok": True, "label": label, "matched": 0, "classified": []}

    results: list[dict[str, Any]] = []
    cache_hits = 0
    cache_creates = 0
    total_in = 0
    total_out = 0

    for i, mid in enumerate(ids, start=1):
        try:
            r = classify_message(mid, categories, model=model_name)
        except Exception as exc:  # noqa: BLE001
            log.exception("classify failed for %s", mid)
            results.append({"id": mid, "ok": False, "error": str(exc)})
            continue
        results.append(r)
        u = r.get("usage", {})
        total_in += u.get("input_tokens", 0)
        total_out += u.get("output_tokens", 0)
        cache_hits += u.get("cache_read_input_tokens", 0)
        cache_creates += u.get("cache_creation_input_tokens", 0)
        # Gentle pacing — Anthropic's Haiku quota is generous but bursts can RL.
        if i < len(ids):
            time.sleep(0.05)

    # Build proposed moves.
    by_name, _ = bulk._label_index()
    moves: list[dict[str, Any]] = []
    applied_ids: dict[str, list[str]] = {}  # target label → ids moved
    for r in results:
        if not r.get("ok"):
            continue
        cat = r.get("category")
        conf = r.get("confidence", 0.0)
        target = category_to_label.get(cat)
        if not target:
            continue
        if target == label:
            continue
        entry = {
            "id": r["id"],
            "subject": r.get("subject"),
            "category": cat,
            "confidence": conf,
            "target": target,
            "would_move": conf >= min_confidence,
        }
        moves.append(entry)
        if apply and entry["would_move"]:
            applied_ids.setdefault(target, []).append(r["id"])

    applied_summary: list[dict[str, Any]] = []
    if apply and applied_ids:
        svc = _gmail()
        for target, mids in applied_ids.items():
            if target not in by_name:
                applied_summary.append({"target": target, "ok": False, "error": "unknown label"})
                continue
            add_id = by_name[target]
            remove_id = by_name.get(label)
            for chunk in bulk._chunks(mids, bulk.BATCH_MODIFY_CHUNK):
                body = {
                    "ids": chunk,
                    "addLabelIds": [add_id],
                    "removeLabelIds": [remove_id] if remove_id else [],
                }
                with_retry(
                    lambda b=body: svc.users().messages().batchModify(userId="me", body=b).execute()
                )
            applied_summary.append({"target": target, "ok": True, "moved": len(mids)})

    return {
        "ok": True,
        "label": label,
        "model": model_name,
        "matched": len(ids),
        "classified": results,
        "proposed_moves": moves,
        "applied": applied_summary,
        "apply": apply,
        "min_confidence": min_confidence,
        "usage_total": {
            "input_tokens": total_in,
            "output_tokens": total_out,
            "cache_read_input_tokens": cache_hits,
            "cache_creation_input_tokens": cache_creates,
        },
    }
