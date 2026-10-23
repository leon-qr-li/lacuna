"""Cloudflare Turnstile: the human check on the sign-in and 申请试用 forms (decision 2026-10-21-app-sign-in).

On when the server has ``TURNSTILE_SITE_KEY`` and ``TURNSTILE_SECRET_KEY`` (deploy/provision.py makes the
widget once the site door is "open"); off everywhere else, so a development checkout and the tests need
nothing. The page shows Cloudflare's widget (usually no click needed) and sends its one-time token; the
server asks Cloudflare whether the token is good before checking the password.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def site_key() -> str | None:
    """The public key the page needs to show the widget, or None when the check is off."""
    k, s = os.environ.get("TURNSTILE_SITE_KEY", "").strip(), os.environ.get("TURNSTILE_SECRET_KEY", "").strip()
    return k if k and s else None


class Verifier:
    """Asks Cloudflare about a token. Tests pass a fake with the same ``ok(token, ip)``."""

    def __init__(self, secret: str | None = None):
        self.secret = secret if secret is not None else os.environ.get("TURNSTILE_SECRET_KEY", "").strip()

    def ok(self, token: str | None, ip: str | None = None) -> bool:
        if not token:
            return False
        data = {"secret": self.secret, "response": token}
        if ip:
            data["remoteip"] = ip
        req = urllib.request.Request(VERIFY_URL, data=urllib.parse.urlencode(data).encode(), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return bool(json.loads(r.read()).get("success"))
        except (OSError, ValueError):
            return False          # can't ask Cloudflare: refuse (the person tries again)
