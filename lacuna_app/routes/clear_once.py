"""One-time clean-out of the cloud workspace at startup. See lacuna_app/clear_once.py."""
from __future__ import annotations

import logging

from .. import clear_once, cloud
from ..learning import Learning

log = logging.getLogger("lacuna.clear_once")


def register(app, ctx) -> None:
    if not cloud.enabled() or ctx.option("space_child") or clear_once.done(ctx.ws):
        return

    def keep_learning(episode_id: str) -> None:
        # same snapshot as 「永久删除」 (routes/archive.py): what 「学到的规则」 learns from
        ctx.provide("learning", lambda: Learning(ctx.ws)).overview([ctx.peek(episode_id)])

    def release(episode_id: str) -> None:
        with ctx.lock:
            ctx.episodes.pop(episode_id, None)
            ctx._alive.pop(episode_id, None)

    out = clear_once.run(ctx.ws, keep_learning=keep_learning, release=release)
    log.warning("clean-out: %d episodes deleted, %d kept for the next start", len(out["deleted"]), len(out["failed"]))
