"""`gsuite auth --expect <email>`: a login from the wrong account is never saved.

Every instance shares one OAuth client, so a token is valid in any config dir.
On 2026-10-06 two accounts' logins were saved into each other's dirs and both
"worked" against the wrong mailbox. `expect` makes the account part of the check.
"""

from __future__ import annotations

import pytest

from gsuite import auth


class _Flow:
    """Stands in for InstalledAppFlow: records how the browser step was started."""

    def __init__(self):
        self.kwargs = None

    def run_local_server(self, **kwargs):
        self.kwargs = kwargs
        return object()  # the credentials; only passed along


@pytest.fixture
def flow(monkeypatch):
    fake = _Flow()
    saved = []
    monkeypatch.setattr(auth, "_load_client_config", lambda: {})
    monkeypatch.setattr(auth.InstalledAppFlow, "from_client_config", lambda *a, **k: fake)
    monkeypatch.setattr(auth, "_read_tokens", lambda: None)
    monkeypatch.setattr(auth, "_creds_to_tokens", lambda creds, prev: {"saved": True})
    monkeypatch.setattr(auth, "_write_tokens", saved.append)
    monkeypatch.delenv("GSUITE_AUTH_PORT", raising=False)
    fake.saved = saved
    return fake


def test_matching_account_is_saved_and_preselected(flow, monkeypatch):
    monkeypatch.setattr(auth, "_signed_in_address", lambda creds: "jaded423@gmail.com")
    auth.run_auth_flow(["scope"], expect="Jaded423@gmail.com")
    assert flow.kwargs["login_hint"] == "Jaded423@gmail.com"
    assert flow.saved == [{"saved": True}]


def test_other_account_is_refused_and_nothing_saved(flow, monkeypatch):
    monkeypatch.setattr(auth, "_signed_in_address", lambda creds: "brown.joshua.david@gmail.com")
    with pytest.raises(auth.WrongAccountError, match="signed in as brown.joshua.david@gmail.com"):
        auth.run_auth_flow(["scope"], expect="jaded423@gmail.com")
    assert flow.saved == []


def test_unknown_account_is_refused_not_assumed(flow, monkeypatch):
    def cannot_tell(creds):
        raise RuntimeError("insufficient scope")

    monkeypatch.setattr(auth, "_signed_in_address", cannot_tell)
    with pytest.raises(auth.WrongAccountError, match="could not confirm"):
        auth.run_auth_flow(["scope"], expect="jaded423@gmail.com")
    assert flow.saved == []


def test_without_expect_nothing_is_checked(flow, monkeypatch):
    def must_not_run(creds):
        raise AssertionError("no account was named, so none is looked up")

    monkeypatch.setattr(auth, "_signed_in_address", must_not_run)
    auth.run_auth_flow(["scope"])
    assert "login_hint" not in flow.kwargs
    assert flow.saved == [{"saved": True}]
