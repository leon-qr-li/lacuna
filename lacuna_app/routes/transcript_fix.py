"""Proofread an episode's transcript against the show's names again (decision `transcript-terms`):
the words of an episode imported before the import did it, or after 项目设置 got new terms."""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import HTTPException

from .. import transcript_fix as tf
from ..server import USAGE_LOG, log_usage
from .episodes import PlayheadBody

BACKUP = "transcript.before_fix.json"


def register(app, ctx) -> None:
    get, mutate = ctx.get, ctx.mutate
    fixer = ctx.provide("transcript_fixer", tf.TranscriptFixer)

    @app.post("/api/episodes/{episode_id}/transcript/fix")
    def fix(episode_id: str, body: PlayheadBody):
        ep = get(episode_id)
        if not ep.transcript:
            raise HTTPException(409, "this episode has no transcript")
        with ep.lock:
            lines = tf.lines_from_transcript(ep.transcript)
            title = str(ep.meta.get("title") or "")
            hosts = list(ep.transcript.get("tracks", {}))
        g = tf.glossary_for(ctx.ws.root, title, hosts)
        # the model is asked without holding the episode: playing and editing go on meanwhile
        fixes = fixer.propose(lines, g, on_usage=lambda u: log_usage(ctx.ws.root / USAGE_LOG, episode_id, u))

        def apply() -> dict:
            with ep.lock:
                current = tf.lines_from_transcript(ep.transcript)
                done = tf.apply(current, fixes)
                if done:
                    name = Path(ep.meta.get("transcript") or "transcript.json").name
                    if not (ep.dir / BACKUP).is_file():
                        shutil.copy2(ep.dir / name, ep.dir / BACKUP)
                    ep.set_transcript(tf.transcript_from_lines(ep.transcript, current))
            return {"fixes": tf.summary(done), "changed": sum(f["count"] for f in done),
                    "ai": fixer.available}
        return mutate(ep, body.playhead, apply)
