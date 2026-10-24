"""Audio-hour metering (lacuna_app/quota.py): one Meter for the whole server, built by the main app and handed
to every show's app (routes/spaces.py SHARED), whose importer asks it before an import and tells it after one
(routes/imports.py)."""
from __future__ import annotations

from ..quota import Meter


def register(app, ctx) -> None:
    if ctx.option("space_child"):
        return
    ctx.provide("meter", lambda: Meter(app.state))


def register_last(app, ctx) -> None:
    if ctx.option("space_child"):
        return
    auth = getattr(app.state, "auth", None)
    meter = ctx.provide("meter")
    if auth is not None and hasattr(auth, "on_deleted"):
        auth.on_deleted.append(lambda email: meter.forget(email) if meter.on else None)
