"""OAuth credential management and Google API service factory.

Design goals (per CLAUDE.md):
- Reuse the pre-granted token file at ~/.config/gsuite/tokens.json.
- Proactively refresh when within 5 minutes of expiry, to avoid the 401-ping-pong
  we hit with @gongrzhe.
- Retry once on 401 after a forced refresh, so one-off clock skews or token
  revocations don't surface as tool errors.
- The browser consent flow is only invoked by `gsuite auth` — the server
  never prompts mid-session (stdout is reserved for MCP protocol).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .settings import OAUTH_CLIENT_PATH, TOKENS_PATH, load_settings, scope_gaps

log = logging.getLogger("gsuite.auth")

# Refresh this many seconds before the stated expiry. Gmail is strict enough
# that cutting it closer produces mid-request 401s under bursty bulk ops.
REFRESH_MARGIN_SEC = 300

T = TypeVar("T")


class AuthError(RuntimeError):
    """Raised when OAuth state is unusable (missing files, no refresh_token, etc.)."""


def _load_client_config() -> dict[str, Any]:
    if not OAUTH_CLIENT_PATH.exists():
        raise AuthError(
            f"OAuth client file not found at {OAUTH_CLIENT_PATH}. "
            "Copy the Desktop-type client JSON from GCP Console."
        )
    return json.loads(OAUTH_CLIENT_PATH.read_text())


def _read_tokens() -> dict[str, Any] | None:
    if not TOKENS_PATH.exists():
        return None
    return json.loads(TOKENS_PATH.read_text())


def _write_tokens(data: dict[str, Any]) -> None:
    TOKENS_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKENS_PATH.write_text(json.dumps(data, indent=2) + "\n")
    TOKENS_PATH.chmod(0o600)


def _tokens_to_creds(tokens: dict[str, Any], client: dict[str, Any]) -> Credentials:
    installed = client["installed"]
    scopes = tokens.get("scope", "").split()
    return Credentials(
        token=tokens.get("access_token"),
        refresh_token=tokens.get("refresh_token"),
        token_uri=installed["token_uri"],
        client_id=installed["client_id"],
        client_secret=installed["client_secret"],
        scopes=scopes,
    )


def _creds_to_tokens(creds: Credentials, prev: dict[str, Any] | None) -> dict[str, Any]:
    """Merge refreshed creds back into on-disk token shape, preserving scope."""
    expiry_ts = int(creds.expiry.timestamp()) if creds.expiry else 0
    scope_str = " ".join(sorted(creds.scopes or []))
    if prev and prev.get("scope") and not scope_str:
        scope_str = prev["scope"]
    return {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token or (prev or {}).get("refresh_token"),
        "scope": scope_str,
        "token_type": "Bearer",
        "expires_in": 3599,
        "_expiry_ts": expiry_ts,
    }


def _needs_refresh(tokens: dict[str, Any]) -> bool:
    expiry = int(tokens.get("_expiry_ts") or 0)
    if expiry == 0:
        return True
    return time.time() + REFRESH_MARGIN_SEC >= expiry


def get_credentials(force_refresh: bool = False) -> Credentials:
    """Return a live `Credentials` object, refreshing if near expiry."""
    tokens = _read_tokens()
    if tokens is None:
        raise AuthError(
            f"No tokens at {TOKENS_PATH}. Run `gsuite auth` to authorize."
        )
    client = _load_client_config()
    creds = _tokens_to_creds(tokens, client)
    if force_refresh or _needs_refresh(tokens):
        if not creds.refresh_token:
            raise AuthError(
                "Token file has no refresh_token. Run `gsuite auth`."
            )
        log.info("refreshing access token (margin=%ss)", REFRESH_MARGIN_SEC)
        creds.refresh(Request())
        _write_tokens(_creds_to_tokens(creds, tokens))
    return creds


def granted_scopes() -> set[str]:
    """Scopes currently held in tokens.json."""
    tokens = _read_tokens()
    if not tokens:
        return set()
    return set((tokens.get("scope") or "").split())


def run_auth_flow(scopes: list[str]) -> Credentials:
    """Kick off the browser OAuth flow for the requested scope set.

    Called by `gsuite auth`. Uses the installed-app / local-server flow,
    which opens a browser and listens on localhost for the callback.
    """
    client = _load_client_config()
    flow = InstalledAppFlow.from_client_config(client, scopes=scopes)
    creds = flow.run_local_server(port=0, open_browser=True)
    _write_tokens(_creds_to_tokens(creds, _read_tokens()))
    return creds


# --- service factory ---------------------------------------------------------

_SERVICE_VERSIONS = {
    "gmail": "v1",
    "drive": "v3",
    "calendar": "v3",
    "docs": "v1",
    "sheets": "v4",
    "slides": "v1",
    "tasks": "v1",
}


def build_service(api: str, version: str | None = None):
    """Return a Google API client for the requested service."""
    creds = get_credentials()
    v = version or _SERVICE_VERSIONS.get(api)
    if v is None:
        raise ValueError(f"unknown api {api!r}; specify version explicitly")
    # cache_discovery=False avoids noisy warnings on macOS when the discovery
    # cache dir is not writable.
    return build(api, v, credentials=creds, cache_discovery=False)


# --- rate limiting + retry ---------------------------------------------------

# Gmail API quota: 250 quota units per user per second (a read is 5 units, a
# modify is 10+). A conservative 5 request/sec sustained rate with burst of 10
# keeps us well under the per-second ceiling while still clearing a 10k-message
# bulk reclassify in reasonable time (~35 minutes).
_DEFAULT_RATE_PER_SEC = 5.0
_DEFAULT_BURST = 10

# Retry policy for 429 and transient 5xx. Each retry doubles the base delay;
# a server-provided `Retry-After` header overrides the calculated backoff.
_MAX_RETRIES = 5
_BASE_BACKOFF_SEC = 1.0
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class TokenBucket:
    """Thread-safe token bucket limiter.

    Kept here rather than pulled in from a dependency because we want the
    behavior to be obvious and testable — `with_retry` is the one choke point
    every Google API call passes through, so a handful of lines here cover the
    entire server.
    """

    def __init__(self, rate_per_sec: float, burst: int):
        self.rate = rate_per_sec
        self.capacity = burst
        self.tokens = float(burst)
        self.last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, sleeper: Callable[[float], None] = time.sleep) -> float:
        """Block until a token is available; return the seconds waited."""
        with self._lock:
            now = time.monotonic()
            self.tokens = min(
                self.capacity, self.tokens + (now - self.last) * self.rate
            )
            self.last = now
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return 0.0
            need = (1.0 - self.tokens) / self.rate
            self.tokens = 0.0
            self.last = now + need
        sleeper(need)
        return need


_GMAIL_BUCKET = TokenBucket(_DEFAULT_RATE_PER_SEC, _DEFAULT_BURST)


def _retry_delay(exc: HttpError, attempt: int) -> float:
    """Seconds to wait before retrying. Honors `Retry-After` if Google sends it."""
    resp = getattr(exc, "resp", None)
    if resp is not None:
        ra = None
        try:
            ra = resp.get("retry-after")
        except AttributeError:
            pass
        if ra:
            try:
                return float(ra)
            except (TypeError, ValueError):
                pass
    return _BASE_BACKOFF_SEC * (2**attempt)


def _status(exc: HttpError) -> int | None:
    resp = getattr(exc, "resp", None)
    if resp is None:
        return getattr(exc, "status_code", None)
    status = getattr(resp, "status", None)
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


def with_retry(
    fn: Callable[[], T],
    *,
    bucket: TokenBucket | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    max_retries: int = _MAX_RETRIES,
) -> T:
    """Run `fn` under the rate limiter with bounded retries.

    Behavior:
      - Acquire one token from `bucket` before every attempt (rate limiting).
      - On HTTP 401: force-refresh tokens and retry once (covers stale access
        tokens and revoked grants).
      - On HTTP 429 or transient 5xx (500, 502, 503, 504): back off with
        exponential delay (or `Retry-After` if present) and retry up to
        `max_retries` times.
      - All other errors propagate.

    The `sleeper` and `bucket` parameters exist so tests can observe retries
    without actually sleeping. Callers in production pass neither.
    """
    bucket = bucket or _GMAIL_BUCKET
    attempt = 0
    refreshed = False
    while True:
        bucket.acquire(sleeper=sleeper)
        try:
            return fn()
        except HttpError as exc:
            status = _status(exc)
            if status == 401 and not refreshed:
                log.warning("got 401; forcing token refresh and retrying")
                get_credentials(force_refresh=True)
                refreshed = True
                continue
            if status in _RETRYABLE_STATUS and attempt < max_retries:
                delay = _retry_delay(exc, attempt)
                log.warning(
                    "got %s; sleeping %.1fs before retry %d/%d",
                    status, delay, attempt + 1, max_retries,
                )
                sleeper(delay)
                attempt += 1
                continue
            raise


def scope_report() -> dict[str, Any]:
    """Return a snapshot of scope state for `gsuite status`."""
    s = load_settings()
    granted = granted_scopes()
    required = s.required_scopes()
    missing = scope_gaps(granted, required)
    extra = granted - required
    tokens = _read_tokens() or {}
    expiry = int(tokens.get("_expiry_ts") or 0)
    return {
        "tokens_present": bool(tokens),
        "expires_at": expiry,
        "expires_in_sec": max(0, expiry - int(time.time())) if expiry else 0,
        "enabled_features": s.enabled_features(),
        "granted_scopes": sorted(granted),
        "required_scopes": sorted(required),
        "missing_scopes": sorted(missing),
        "extra_scopes": sorted(extra),
        "needs_reauth": bool(missing),
    }
