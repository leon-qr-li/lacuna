"""Leon's stutter rules, added once at startup in the cloud. See lacuna_app/stutter_rule_once.py."""
from __future__ import annotations

import logging

from .. import cloud, stutter_rule_once
from ..chat_learning import ChatAsks
from ..learning import Learning

log = logging.getLogger("lacuna.stutter_rule_once")


def register(app, ctx) -> None:
    if not cloud.enabled() or ctx.option("space_child") or stutter_rule_once.done(ctx.ws):
        return
    try:
        added = stutter_rule_once.run(ctx.ws, ctx.provide("learning", lambda: Learning(ctx.ws)),
                                      ctx.provide("chat_asks", lambda: ChatAsks(ctx.ws)))
    except Exception:                  # the site must start; tried again at the next start
        log.exception("stutter rules: not added")
        return
    log.warning("stutter rules in force: %s", added)
