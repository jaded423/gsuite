"""Structured error helper for tool handlers.

Per CLAUDE.md's robustness contract, every tool failure should return a dict
with `error` (message) and `retryable` (bool), plus optional context. The
server wraps *uncaught* exceptions in the same shape (see `server.py`), so
handler-level validation errors go through this helper instead of ad-hoc
`{"ok": False, "error": ...}` returns.

`retryable=False` is right for input validation and missing-confirm guards
(the caller has to fix something before retrying). Transient failures — API
timeouts, quota, 5xx — are handled by `with_retry` in auth.py and never
reach this helper.
"""

from __future__ import annotations

from typing import Any


def error(message: str, *, retryable: bool = False, **extra: Any) -> dict[str, Any]:
    """Build a structured error dict. Extra kwargs are merged into the payload."""
    return {"ok": False, "error": message, "retryable": retryable, **extra}
