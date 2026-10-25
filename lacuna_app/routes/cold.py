"""Cloud storage for the audio of episodes not used for 14 days (lacuna_app/cold.py). One ColdStore for the
whole server, built by the main app and handed to every show's app (routes/spaces.py SHARED): opening an
episode (AppContext.get) brings its audio back. An hourly sweep moves out what may go, in every show; once a day
objects nothing refers to any more are deleted. The staging site only reads."""
from __future__ import annotations

import os
import threading
import time
import traceback

from .. import cloud
from ..cold import ColdStore
from ..r2 import Bucket
from ..spaces import MAIN
from ..store import Workspace

SWEEP_S = 3600
GC_EVERY_S = 86400


def shows(app, ctx):
    """(workspace, busy(episode id)) for every show on the server."""
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

    out.append((ctx.ws, busy_of(app.state, ctx)))
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
                        else (lambda _eid: False)))
    return out


def register(app, ctx) -> None:
    if ctx.option("space_child"):
        return
    freezing = not cloud.staging() and os.environ.get("LACUNA_COLD", "on") != "off"
    store = ctx.provide("cold", lambda: ColdStore(Bucket.from_env(), freezing=freezing))
    if store is None or not store.freezing or ctx.option("no_cold_sweep"):
        return

    def loop():
        last_gc = 0.0
        while True:
            time.sleep(SWEEP_S)
            try:
                out = store.sweep(shows(app, ctx))
                if out["moved"] or out["failed"]:
                    print(f"LACUNA: audio moved to cloud storage: {out}", flush=True)
                if time.time() - last_gc > GC_EVERY_S:
                    last_gc = time.time()
                    store.gc([ctx.ws.root])
            except Exception:          # noqa: BLE001 - tried again next round
                traceback.print_exc()

    threading.Thread(target=loop, daemon=True, name="cold-sweep").start()
