"""The proper-noun check made at import (name_check.py): what it changed in an episode's transcript, and
putting one back as heard (that pair is then left alone by later imports and the show notes)."""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel, Field

from .. import name_check as nc
from .. import transcript_fix as tf
from ..store import atomic_write_json, read_json
from .episodes import PlayheadBody
from .transcript_fix import BACKUP


class KeepBody(PlayheadBody):
    wrong: str = Field(min_length=1, max_length=200)
    right: str = Field(min_length=1, max_length=200)


def register(app, ctx) -> None:
    get, mutate = ctx.get, ctx.mutate

    def rows(ep) -> list[dict]:
        p = ep.dir / nc.EPISODE_FILE
        try:
            return list(read_json(p).get("rows") or []) if p.is_file() else []
        except (OSError, ValueError, AttributeError):
            return []

    @app.get("/api/episodes/{episode_id}/names")
    def names(episode_id: str):
        """{"rows": [{"wrong", "right", "why", "count", "places", "state"}], "on": the project's setting}."""
        ep = ctx.peek(episode_id)
        return {"rows": rows(ep), "on": nc.enabled(ctx.ws.root)}

    @app.post("/api/episodes/{episode_id}/names/keep")
    def keep(episode_id: str, body: KeepBody):
        """Put one fix back as heard: `right` becomes `wrong` again where the check wrote it."""
        ep = get(episode_id)

        def apply() -> dict:
            with ep.lock:
                all_rows = rows(ep)
                row = next((r for r in all_rows if r["wrong"] == body.wrong and r["right"] == body.right), None)
                if row is None or not ep.transcript:
                    raise HTTPException(404, "no such fix")
                lines = tf.lines_from_transcript(ep.transcript)
                n = 0
                for ln in lines:
                    if not ln.words:
                        continue
                    a, b = ln.words[0]["start"], ln.words[-1]["end"]
                    if any(p["speaker"] == ln.speaker and p["start"] < b + 0.05 and p["end"] > a - 0.05 for p in row["places"]):
                        n += tf.replace(ln.words, body.right, body.wrong)
                if n:
                    name = Path(ep.meta.get("transcript") or "transcript.json").name
                    if not (ep.dir / BACKUP).is_file():
                        shutil.copy2(ep.dir / name, ep.dir / BACKUP)
                    ep.set_transcript(tf.transcript_from_lines(ep.transcript, lines))
                row["state"] = "kept"
                atomic_write_json(ep.dir / nc.EPISODE_FILE, {"rows": all_rows})
            nc.keep(ctx.ws.root, body.wrong, body.right)
            return {"names": all_rows, "changed": n}
        return mutate(ep, body.playhead, apply)
