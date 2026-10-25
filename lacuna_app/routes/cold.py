"""Where audio lives and how long (lacuna_app/cold.py, lacuna_app/retention.py). One ColdStore for the whole server,
built by the main app and handed to every show's app (routes/spaces.py SHARED): opening an episode (AppContext.get)
brings its audio back from cloud storage. An hourly round on the cloud site, over every show: audio of episodes not
used for 14 days moves out, old exports go, raw tracks past their 12 months go (when the owner turned that on) after
a reminder; once a day objects nothing refers to any more are deleted from R2. The staging site only reads."""
from __future__ import annotations

import os
import threading
import time
import traceback

from .. import cloud, notice_mail, retention
from ..cold import ColdStore
from ..i18n import speaking
from ..r2 import Bucket
from ..spaces import MAIN
from ..store import Workspace

SWEEP_S = 3600
GC_EVERY_S = 86400


def shows(app, ctx):
    """(workspace, busy(episode id), {"sid", "email", "title"}) for every show on the server."""
    out = []
    spaces = getattr(app.state, "spaces", None)
    children = getattr(app.state, "space_apps", {}) or {}

    def busy_of(state, c):
        def busy(eid: str) -> bool:
            if c is not None and c.loaded(eid) is not None:
                return True
            imp, exp = getattr(state, "importer", None), getattr(state, "exporter", None)
            return bool((imp is not None and eid in imp.active()) or (exp is not None and exp._running == eid))
        return busy

    def who(sid):
        if spaces is None:
            return {"sid": sid, "email": None, "title": ""}
        try:
            return {"sid": sid, "email": spaces.creator(sid), "title": spaces.title(sid)}
        except (KeyError, OSError):
            return {"sid": sid, "email": None, "title": ""}

    out.append((ctx.ws, busy_of(app.state, ctx), who(MAIN)))
    if spaces is not None:
        for sid in list(spaces.spaces):
            if sid == MAIN:
                continue
            try:
                folder = spaces.path(sid)
            except (KeyError, OSError):
                continue
            child = children.get(sid)
            st = child.state if child is not None else None
            out.append((Workspace(folder), busy_of(st, getattr(st, "ctx", None)) if st is not None
                        else (lambda _eid: False), who(sid)))
    return out


def reminder(app, show: dict, episodes: list[dict]) -> None:
    """The 30-day email before raw tracks are deleted (retention.py), to the show's creator, in their language."""
    auth = getattr(app.state, "auth", None)
    if auth is None or getattr(auth, "mailer", None) is None:
        raise RuntimeError("no mail")
    user = auth.users.get(show["email"]) or {}
    origin = (os.environ.get("LACUNA_PUBLIC_URL") or "").rstrip("/")
    with speaking(user.get("lang") or "zh"):
        m = notice_mail.raw_tracks_reminder(show.get("title") or "", episodes, origin or None)
        auth.mailer.send(auth.config["sender"], show["email"], m["subject"], m["text"], html=m.get("html"),
                         inline=m.get("inline"))


def upkeep(app, ctx, store: ColdStore | None, last_gc: list[float]) -> dict:
    """One round: move old episodes' audio out, keep only the latest exports, raw-track retention, clean R2."""
    every = shows(app, ctx)
    out: dict = {}
    if store is not None and store.freezing:
        out["cold"] = store.sweep([(w, b) for w, b, _ in every])
    auth = getattr(app.state, "auth", None)
    if auth is not None and getattr(auth, "db", None) is not None:
        out["retention"] = retention.sweep(every, auth.db, lambda show, eps: reminder(app, show, eps))
    if store is not None and store.freezing and time.time() - last_gc[0] > GC_EVERY_S:
        last_gc[0] = time.time()
        out["gc"] = store.gc([ctx.ws.root])
    return out


def register(app, ctx) -> None:
    if ctx.option("space_child"):
        return
    freezing = not cloud.staging() and os.environ.get("LACUNA_COLD", "on") != "off"
    store = ctx.provide("cold", lambda: ColdStore(Bucket.from_env(), freezing=freezing))
    app.state.storage_upkeep = lambda: upkeep(app, ctx, store, [0.0])
    # the staging site works on a copy: it never moves, deletes or emails anything
    if cloud.staging() or ctx.option("no_cold_sweep") or not cloud.enabled():
        return

    def loop():
        last_gc = [0.0]
        while True:
            time.sleep(SWEEP_S)
            try:
                out = upkeep(app, ctx, store, last_gc)
                if any(any(p.values()) if isinstance(p, dict) else p for p in out.values()):
                    print(f"LACUNA: storage upkeep: {out}", flush=True)
            except Exception:          # noqa: BLE001 - tried again next round
                traceback.print_exc()

    threading.Thread(target=loop, daemon=True, name="storage-upkeep").start()
