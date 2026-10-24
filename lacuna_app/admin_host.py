"""The admin site's address (decision 2026-10-24-admin-site): admin.<domain> answers only the admin, the main
site never answers the admin.

``AdminHost`` is the outermost ASGI layer of the app (routes/admin.py installs it after every feature):

* a request for the admin host goes to the admin app (lacuna_app/admin_api.py) and never reaches the main
  site's routes, sessions or workspace dispatcher. In the cloud it must carry a valid token from the admin's
  own Cloudflare Access application (``CF_ADMIN_ACCESS_AUD``, owner-only list, never switched off); the main
  site's Access token has another audience and is refused. Every admin answer carries strict security
  headers (``HEADERS``): no script but our own, no framing, no referrer.
* any other host: ``/api/admin/*`` answers 404, as if it did not exist; the rest is the main site. Its 5xx
  answers are counted for the admin's 系统健康 page (``on_error``).

The admin host is ``LACUNA_ADMIN_HOST`` (deploy/provision.py sets ``admin.<domain>``); a development checkout
uses ``admin.localhost`` (browsers send it to this computer). In the cloud without it the admin is off.
"""
from __future__ import annotations

import os
from typing import Callable

from . import cloud

ENV = "LACUNA_ADMIN_HOST"
AUD_ENV = "CF_ADMIN_ACCESS_AUD"
LOCAL_HOST = "admin.localhost"
API = "/api/admin/"

CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
       "font-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; "
       "form-action 'self'")
HEADERS = [
    (b"content-security-policy", CSP.encode()),
    (b"x-frame-options", b"DENY"),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"cross-origin-opener-policy", b"same-origin"),
    (b"cross-origin-resource-policy", b"same-origin"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=()"),
    (b"x-robots-tag", b"noindex, nofollow"),
]


def admin_host() -> str | None:
    v = os.environ.get(ENV, "").strip().lower()
    if v:
        return v
    return None if cloud.enabled() else LOCAL_HOST


def host_of(scope) -> str:
    raw = next((v for k, v in scope.get("headers") or [] if k == b"host"), b"").decode("latin-1").strip().lower()
    if raw.startswith("["):                       # [::1]:8765
        return raw.split("]")[0] + "]"
    return raw.rsplit(":", 1)[0] if ":" in raw else raw


def access_verifier() -> cloud.AccessVerifier | None:
    """The admin's own Access check in the cloud (None: not configured, and the admin then refuses everything)."""
    aud = os.environ.get(AUD_ENV, "").strip()
    team = os.environ.get("CF_ACCESS_TEAM_DOMAIN", "").strip()
    if not (aud and team):
        return None
    return cloud.AccessVerifier(team, aud)


async def _plain(send, status: int, body: bytes, extra: list | None = None) -> None:
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"text/plain; charset=utf-8"), *HEADERS, *(extra or [])]})
    await send({"type": "http.response.body", "body": body})


class AdminHost:
    def __init__(self, app, admin_app, verifier: cloud.AccessVerifier | None, cloud_on: bool,
                 on_error: Callable[[str, str, int], None] | None = None, host: Callable[[], str | None] = admin_host):
        self.app, self.admin, self.verifier, self.cloud_on = app, admin_app, verifier, cloud_on
        self.on_error, self.host = on_error, host

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        want = self.host()
        if want and host_of(scope) == want:
            return await self._admin(scope, receive, send)
        if scope["type"] == "http" and (scope["path"] == API.rstrip("/") or scope["path"].startswith(API)):
            await send({"type": "http.response.start", "status": 404,
                        "headers": [(b"content-type", b"application/json")]})
            return await send({"type": "http.response.body", "body": b'{"detail":"Not Found"}'})
        if scope["type"] != "http" or self.on_error is None:
            return await self.app(scope, receive, send)

        async def watch(msg):
            if msg["type"] == "http.response.start" and msg["status"] >= 500:
                try:
                    self.on_error(scope["method"], scope["path"], msg["status"])
                except Exception:       # noqa: BLE001 - counting must never break a request
                    pass
            await send(msg)
        return await self.app(scope, receive, watch)

    async def _admin(self, scope, receive, send):
        if scope["type"] == "websocket":
            return await send({"type": "websocket.close", "code": 1008})
        state = scope.setdefault("state", {})
        if self.cloud_on:
            if self.verifier is None:
                return await _plain(send, 503, b"LACUNA admin is not connected to its access check yet.")
            token = dict(scope.get("headers") or []).get(cloud.ACCESS_HEADER, b"").decode("latin-1")
            claims = self.verifier.verify(token) if token else None
            if claims is None:
                return await _plain(send, 403, b"Forbidden")
            state["admin_access_email"] = str(claims.get("email") or "").strip().lower() or None

        async def secured(msg):
            if msg["type"] == "http.response.start":
                names = {k.lower() for k, _ in msg.get("headers") or []}
                msg = dict(msg)
                msg["headers"] = [*(msg.get("headers") or []), *[h for h in HEADERS if h[0] not in names]]
                if scope["path"].startswith("/api/") and b"cache-control" not in names:
                    msg["headers"].append((b"cache-control", b"no-store"))
            await send(msg)
        return await self.admin(scope, receive, secured)
