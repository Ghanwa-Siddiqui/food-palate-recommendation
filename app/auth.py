"""Supabase Auth adapter with sanitized, structured failure handling."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

import httpx
from gotrue.errors import (
    AuthApiError,
    AuthRetryableError,
    AuthUnknownError,
    AuthWeakPasswordError,
)
from gotrue.errors import (
    AuthError as GoTrueAuthError,
)
from supabase import create_client

from .config import SUPABASE_PUBLISHABLE_KEY, SUPABASE_URL

logger = logging.getLogger(__name__)


class AuthError(Exception):
    public_message = "Authentication could not be completed."
    http_status = 503

    def __init__(self, message: str | None = None) -> None:
        if message is not None:
            self.public_message = message
        super().__init__(self.public_message)


class DuplicateSignupError(AuthError):
    public_message = "An account with this email already exists."
    http_status = 409


class InvalidEmailError(AuthError):
    public_message = "Enter a valid email address."
    http_status = 422


class WeakPasswordError(AuthError):
    public_message = "Choose a stronger password that meets the password policy."
    http_status = 422


class AuthRateLimitError(AuthError):
    public_message = "Too many attempts. Please wait before trying again."
    http_status = 429


class InvalidCredentialsError(AuthError):
    public_message = "Email or password is incorrect."
    http_status = 401


class AuthUnavailableError(AuthError):
    public_message = "Authentication is temporarily unavailable."
    http_status = 503


class AuthResponseError(AuthUnavailableError):
    pass


@dataclass(frozen=True)
class AuthUser:
    id: UUID
    email: str
    name: str


@dataclass(frozen=True)
class AuthSession:
    user: AuthUser
    access_token: str
    refresh_token: str


@dataclass(frozen=True)
class SignupResult:
    user: AuthUser
    session: AuthSession | None
    verification_required: bool


class AuthProvider(Protocol):
    def signup(
        self, email: str, password: str, name: str, role: str = "customer"
    ) -> SignupResult: ...
    def login(self, email: str, password: str) -> AuthSession: ...
    def verify(self, access_token: str) -> AuthUser: ...
    def refresh(self, refresh_token: str) -> AuthSession: ...
    def logout(self, access_token: str, refresh_token: str) -> None: ...


def _safe_log(operation: str, exc: Exception) -> None:
    status = getattr(exc, "status", None)
    code = getattr(exc, "code", None)
    logger.warning(
        "supabase_auth_failure operation=%s exception=%s status=%s code=%s",
        operation,
        type(exc).__name__,
        status if isinstance(status, int) and 100 <= status <= 599 else "unknown",
        code if code in _SAFE_LOG_CODES else "unknown",
    )


def _auth_user(raw) -> AuthUser:
    if raw is None:
        raise AuthResponseError()
    raw_id = getattr(raw, "id", None)
    raw_email = getattr(raw, "email", None)
    if not raw_id or not isinstance(raw_email, str) or not raw_email:
        raise AuthResponseError()
    metadata = getattr(raw, "user_metadata", None) or {}
    if not isinstance(metadata, dict):
        metadata = {}
    name = str(
        metadata.get("name") or metadata.get("full_name") or raw_email.split("@", 1)[0]
    )
    try:
        return AuthUser(id=UUID(str(raw_id)), email=raw_email, name=name)
    except (ValueError, TypeError) as exc:
        raise AuthResponseError() from exc


def _session(raw_session) -> AuthSession:
    if raw_session is None:
        raise AuthResponseError()
    access_token = getattr(raw_session, "access_token", None)
    refresh_token = getattr(raw_session, "refresh_token", None)
    raw_user = getattr(raw_session, "user", None)
    if not isinstance(access_token, str) or not isinstance(refresh_token, str):
        raise AuthResponseError()
    return AuthSession(
        user=_auth_user(raw_user),
        access_token=access_token,
        refresh_token=refresh_token,
    )


_DUPLICATE_CODES = {"email_exists", "user_already_exists", "identity_already_exists"}
_INVALID_EMAIL_CODES = {
    "email_address_invalid",
    "email_address_not_authorized",
}
_RATE_LIMIT_CODES = {
    "over_request_rate_limit",
    "over_email_send_rate_limit",
    "over_sms_send_rate_limit",
}
_SAFE_LOG_CODES = (
    _DUPLICATE_CODES
    | _INVALID_EMAIL_CODES
    | _RATE_LIMIT_CODES
    | {
        "weak_password",
        "invalid_credentials",
        "email_not_confirmed",
        "request_timeout",
        "signup_disabled",
        "email_provider_disabled",
        "unexpected_failure",
    }
)


def _classify_signup_error(exc: Exception) -> AuthError:
    _safe_log("signup", exc)
    code = getattr(exc, "code", None)
    status = getattr(exc, "status", None)
    if isinstance(exc, AuthWeakPasswordError) or code == "weak_password":
        return WeakPasswordError()
    if code in _DUPLICATE_CODES or status == 409:
        return DuplicateSignupError()
    if code in _INVALID_EMAIL_CODES:
        return InvalidEmailError()
    if code in _RATE_LIMIT_CODES or status == 429:
        return AuthRateLimitError()
    if isinstance(
        exc, (AuthRetryableError, httpx.TimeoutException, httpx.RequestError)
    ):
        return AuthUnavailableError()
    if isinstance(exc, (AuthApiError, AuthUnknownError, GoTrueAuthError)):
        return AuthUnavailableError()
    return AuthUnavailableError()


class SupabaseAuthProvider:
    def _client(self):
        if not SUPABASE_URL or not SUPABASE_PUBLISHABLE_KEY:
            raise AuthUnavailableError("Authentication is not configured")
        return create_client(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY)

    def signup(
        self, email: str, password: str, name: str, role: str = "customer"
    ) -> SignupResult:
        try:
            response = self._client().auth.sign_up(
                {
                    "email": email,
                    "password": password,
                    "options": {"data": {"name": name, "role": role}},
                }
            )
        except Exception as exc:
            classified = _classify_signup_error(exc)
            raise classified from exc
        if response is None or not hasattr(response, "user"):
            error = AuthResponseError()
            _safe_log("signup", error)
            raise error
        try:
            user = _auth_user(response.user)
            session = (
                _session(response.session) if response.session is not None else None
            )
        except AuthResponseError as exc:
            _safe_log("signup", exc)
            raise
        return SignupResult(
            user=user,
            session=session,
            verification_required=session is None,
        )

    def login(self, email: str, password: str) -> AuthSession:
        try:
            response = self._client().auth.sign_in_with_password(
                {"email": email, "password": password}
            )
        except Exception as exc:
            _safe_log("login", exc)
            code = getattr(exc, "code", None)
            if code == "email_not_confirmed":
                raise InvalidCredentialsError(
                    "Email verification is required before login."
                ) from exc
            if isinstance(exc, AuthRetryableError) or getattr(exc, "status", None) in {
                429,
                500,
                502,
                503,
                504,
            }:
                raise AuthUnavailableError() from exc
            raise InvalidCredentialsError() from exc
        if response is None or getattr(response, "session", None) is None:
            raise InvalidCredentialsError(
                "Email verification is required before login."
            )
        try:
            return _session(response.session)
        except AuthResponseError as exc:
            _safe_log("login", exc)
            raise

    def verify(self, access_token: str) -> AuthUser:
        try:
            response = self._client().auth.get_user(access_token)
            return _auth_user(getattr(response, "user", None))
        except Exception as exc:
            _safe_log("verify", exc)
            raise InvalidCredentialsError("Session is invalid or expired.") from exc

    def refresh(self, refresh_token: str) -> AuthSession:
        try:
            response = self._client().auth.refresh_session(refresh_token)
            return _session(getattr(response, "session", None))
        except Exception as exc:
            _safe_log("refresh", exc)
            raise InvalidCredentialsError("Session is invalid or expired.") from exc

    def logout(self, access_token: str, refresh_token: str) -> None:
        try:
            client = self._client()
            client.auth.set_session(access_token, refresh_token)
            client.auth.sign_out({"scope": "local"})
        except Exception as exc:  # noqa: BLE001 -- local logout must always complete
            _safe_log("logout", exc)


def get_auth_provider() -> AuthProvider:
    return SupabaseAuthProvider()
