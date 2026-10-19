"""Cloud mode wiring (lacuna_app/cloud.py): the Cloudflare Access gate, outermost. Off on the desktop."""
from __future__ import annotations

from .. import cloud
from ..appinfo import current_version
from .auth import _cookie


def register(app, ctx) -> None:
    auth = ctx.provide("auth")

    def signed_in(cookie_header: str) -> bool:
        return bool(auth and auth.who(_cookie(cookie_header)))

    cloud.install(app, signed_in, current_version, verifier=ctx.option("access_verifier"))
