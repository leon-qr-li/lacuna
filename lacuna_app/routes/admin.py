"""The admin site (decision 2026-10-24-admin-site): admin.<domain> for the owner and site admins.

``register_last`` runs after every other feature, so ``AdminHost`` sits outside all of them: the admin host
answers only the admin (lacuna_app/admin_api.py), every other host answers 404 to ``/api/admin/*``. It also
keeps what the main site does feeding the admin: where an invite came from (邀请来源) follows the account when it
joins; an account's hour requests and notes go when it is deleted. And it starts the owner's emails
(lacuna_app/admin_digest.py).
"""
from __future__ import annotations

import os
import threading

from .. import admin_host, cloud
from ..admin_api import build
from ..admin_digest import Digest
from ..admin_store import AdminStore
from ..auth import Auth


def register(app, ctx) -> None:
    """Nothing before the other features: see ``register_last``."""


def register_last(app, ctx) -> None:
    if ctx.option("space_child"):
        return
    auth: Auth = ctx.provide("auth")
    store: AdminStore = ctx.provide("admin_store", lambda: AdminStore(auth.db, auth.now))

    def joined(email: str, invite: dict | None) -> None:
        invited = store.get("invited_sources", {})
        if email in invited:
            store.put("sources", store.get("sources", {}) | {email: invited.pop(email)})
            store.put("invited_sources", invited)

    auth.on_joined.append(joined)
    auth.on_deleted.append(store.forget)

    admin = build(ctx, app, ctx.web_dist)
    verifier = ctx.option("admin_access_verifier") or (admin_host.access_verifier() if cloud.enabled() else None)
    on = ctx.option("admin_cloud")
    app.add_middleware(admin_host.AdminHost, admin_app=admin, verifier=verifier,
                       cloud_on=cloud.enabled() if on is None else bool(on), on_error=store.error)
    host = admin_host.admin_host()
    app.state.admin_url = (f"https://{host}" if cloud.enabled() else f"http://{host}") if host else None

    def send(to: str, m: dict, what: str) -> None:
        try:
            auth.mailer.send(auth.config["sender"], to, m["subject"], m["text"], html=m.get("html"), inline=m.get("inline"))
        except Exception as e:      # noqa: BLE001 - mail is best-effort
            print(f"LACUNA: admin {what} mail failed: {e}", flush=True)

    digest = Digest(auth, store, ctx.provide("admin_data"), app.state.admin_url or "", send)
    app.state.admin_digest = digest
    if not ctx.option("no_admin_loop") and os.environ.get("LACUNA_ADMIN_LOOP", "1") != "0":
        threading.Thread(target=digest.loop, daemon=True, name="admin-digest").start()
