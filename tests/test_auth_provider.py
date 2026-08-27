import logging
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from gotrue.errors import AuthApiError, AuthRetryableError, AuthWeakPasswordError

from app.auth import (
    AuthRateLimitError,
    AuthResponseError,
    AuthUnavailableError,
    DuplicateSignupError,
    InvalidEmailError,
    SupabaseAuthProvider,
    WeakPasswordError,
)

USER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def _user():
    return SimpleNamespace(
        id=USER_ID,
        email="person@example.test",
        user_metadata={"name": "Person"},
    )


def _session(user=None):
    return SimpleNamespace(
        user=user or _user(),
        access_token="access-token-value",
        refresh_token="refresh-token-value",
    )


class StubAuth:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.credentials = None

    def sign_up(self, credentials):
        self.credentials = credentials
        if self.error:
            raise self.error
        return self.response


def _provider(monkeypatch, *, response=None, error=None):
    endpoint = StubAuth(response=response, error=error)
    provider = SupabaseAuthProvider()
    monkeypatch.setattr(provider, "_client", lambda: SimpleNamespace(auth=endpoint))
    return provider, endpoint


def test_signup_payload_and_successful_auto_confirm(monkeypatch):
    provider, endpoint = _provider(
        monkeypatch,
        response=SimpleNamespace(user=_user(), session=_session()),
    )

    result = provider.signup("person@example.test", "safe-password", "Person")

    assert endpoint.credentials == {
        "email": "person@example.test",
        "password": "safe-password",
        "options": {"data": {"name": "Person", "role": "customer"}},
    }
    assert result.user.id == USER_ID
    assert result.session is not None
    assert not result.verification_required


def test_signup_supports_verification_required_response(monkeypatch):
    provider, _ = _provider(
        monkeypatch, response=SimpleNamespace(user=_user(), session=None)
    )

    result = provider.signup("person@example.test", "safe-password", "Person")

    assert result.session is None
    assert result.verification_required


@pytest.mark.parametrize(
    ("sdk_error", "expected"),
    [
        (
            AuthApiError("sensitive duplicate detail", 422, "user_already_exists"),
            DuplicateSignupError,
        ),
        (
            AuthApiError("sensitive invalid detail", 422, "email_address_invalid"),
            InvalidEmailError,
        ),
        (
            AuthWeakPasswordError("sensitive policy detail", 422, ["length"]),
            WeakPasswordError,
        ),
        (
            AuthApiError("sensitive rate detail", 429, "over_request_rate_limit"),
            AuthRateLimitError,
        ),
        (AuthRetryableError("sensitive upstream detail", 503), AuthUnavailableError),
        (
            httpx.ReadTimeout(
                "sensitive timeout detail",
                request=httpx.Request("POST", "https://example.invalid/auth/v1/signup"),
            ),
            AuthUnavailableError,
        ),
    ],
)
def test_signup_classifies_sdk_failures_without_sensitive_logs(
    monkeypatch, caplog, sdk_error, expected
):
    provider, _ = _provider(monkeypatch, error=sdk_error)
    caplog.set_level(logging.WARNING, logger="app.auth")

    with pytest.raises(expected) as captured:
        provider.signup("private@example.test", "private-password", "Private Person")

    assert captured.value.__cause__ is sdk_error
    assert "private@example.test" not in caplog.text
    assert "private-password" not in caplog.text
    assert "sensitive" not in caplog.text
    assert "operation=signup" in caplog.text
    assert type(sdk_error).__name__ in caplog.text


@pytest.mark.parametrize(
    "response",
    [None, SimpleNamespace(session=None), SimpleNamespace(user=None, session=None)],
)
def test_signup_rejects_missing_or_unexpected_user(monkeypatch, response):
    provider, _ = _provider(monkeypatch, response=response)

    with pytest.raises(AuthResponseError):
        provider.signup("person@example.test", "safe-password", "Person")


def test_signup_rejects_malformed_confirmed_session(monkeypatch):
    provider, _ = _provider(
        monkeypatch,
        response=SimpleNamespace(
            user=_user(),
            session=SimpleNamespace(
                user=_user(), access_token=None, refresh_token=None
            ),
        ),
    )

    with pytest.raises(AuthResponseError):
        provider.signup("person@example.test", "safe-password", "Person")
