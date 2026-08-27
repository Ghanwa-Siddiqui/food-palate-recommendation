"""Minimal signed HTTP-only cookie session middleware without external state."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import MutableMapping

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SignedSessionMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        secret_key: str,
        cookie_name: str = "namak_session",
        max_age: int = 604800,
        https_only: bool = False,
    ) -> None:
        self.app = app
        self.key = secret_key.encode()
        self.cookie_name = cookie_name
        self.max_age = max_age
        self.security_flags = "httponly; samesite=lax" + (
            "; secure" if https_only else ""
        )

    def _decode(self, raw: str) -> dict:
        try:
            encoded, signature = raw.rsplit(".", 1)
            expected = hmac.new(self.key, encoded.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                return {}
            padding = "=" * (-len(encoded) % 4)
            return json.loads(base64.urlsafe_b64decode(encoded + padding))
        except (ValueError, TypeError, json.JSONDecodeError):
            return {}

    def _encode(self, session: MutableMapping) -> str:
        payload = json.dumps(dict(session), separators=(",", ":")).encode()
        encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
        signature = hmac.new(self.key, encoded.encode(), hashlib.sha256).hexdigest()
        return f"{encoded}.{signature}"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        cookies = {}
        for part in (
            dict(scope.get("headers", [])).get(b"cookie", b"").decode().split(";")
        ):
            if "=" in part:
                key, value = part.strip().split("=", 1)
                cookies[key] = value
        initial = self._decode(cookies.get(self.cookie_name, ""))
        scope["session"] = dict(initial)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start" and scope["session"] != initial:
                headers = MutableHeaders(scope=message)
                if scope["session"]:
                    value = self._encode(scope["session"])
                    headers.append(
                        "set-cookie",
                        f"{self.cookie_name}={value}; path=/; max-age={self.max_age}; {self.security_flags}",
                    )
                else:
                    headers.append(
                        "set-cookie",
                        f"{self.cookie_name}=null; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT; {self.security_flags}",
                    )
            await send(message)

        await self.app(scope, receive, send_wrapper)
