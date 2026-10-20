"""Proofread an episode's transcript against the show's names again (decision `transcript-terms`):
an episode imported before the import did it, or after the project / system terms changed. The page
asks GET (due?) when an episode opens and then POSTs by itself; nobody has to click."""
from __future__ import annotations

import shutil
import threading
from pathlib import Path

from fastapi import HTTPException

from .. import transcript_fix as tf
from ..server import USAGE_LOG, log_usage
from .episodes import PlayheadBody

BACKUP = "transcript.before_fix.json"


def register(app, ctx) -> None:
    get, mutate = ctx.get, ctx.mutate
    fixer = ctx.provide("transcript_fixer", tf.TranscriptFixer)

    running: set[str] = set()
    lock = threading.Lock()

    def glossary(ep):
        with ep.lock:
            title = str(ep.meta.get("title") or "")
            hosts = list((ep.transcript or {}).get("tracks", {}))
        return tf.glossary_for(ctx.ws.root, title, hosts)

    @app.get("/api/episodes/{episode_id}/transcript/fix")
    def due(episode_id: str):
        """Whether the page should proofread this episode now: it never was with the current terms (an
        episode imported before, or the project / system terms changed since)."""
        ep = get(episode_id)
        if not ep.transcript or not fixer.available:
            return {"due": False}
        with lock:
            if episode_id in running:
                return {"due": False}
        return {"due": tf.checked(ep.dir) != tf.signature(glossary(ep))}

    @app.post("/api/episodes/{episode_id}/transcript/fix")
    def fix(episode_id: str, body: PlayheadBody):
        ep = get(episode_id)
        if not ep.transcript:
            raise HTTPException(409, "this episode has no transcript")
        with lock:
            if episode_id in running:
                raise HTTPException(409, "already being proofread")
            running.add(episode_id)
        try:
            with ep.lock:
                lines = tf.lines_from_transcript(ep.transcript)
            g = glossary(ep)
            # the model is asked without holding the episode: playing and editing go on meanwhile
            fixes, complete = fixer.propose_all(lines, g, on_usage=lambda u: log_usage(ctx.ws.root / USAGE_LOG, episode_id, u))
            if complete:              # a failed request is asked again the next time the episode opens
                tf.mark_checked(ep.dir, g)
        finally:
            with lock:
                running.discard(episode_id)

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
