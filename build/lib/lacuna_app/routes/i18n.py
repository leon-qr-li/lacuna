"""Interface language per request (see ``lacuna_app/i18n.py``): reads the ``lacuna_lang`` cookie."""
from __future__ import annotations

from http.cookies import SimpleCookie

from .. import i18n


class _LangMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        raw = next((v.decode("latin-1") for k, v in scope.get("headers", []) if k == b"cookie"), "")
        cookie = SimpleCookie()
        try:
            cookie.load(raw)
        except Exception:  # a malformed cookie from another app on localhost
            pass
        token = i18n.set_request_lang(cookie[i18n.COOKIE].value if i18n.COOKIE in cookie else None)
        try:
            await self.app(scope, receive, send)
        finally:
            i18n.reset_request_lang(token)


def register(app, ctx) -> None:
    app.add_middleware(_LangMiddleware)
