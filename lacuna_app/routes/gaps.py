"""间隙 (docs/decisions/2026-10-30-edit-gaps.md): open a silent stretch between two sentences while editing, and
fill the gaps with interludes from the music library. The voice edit is never touched (lacuna_app/gaps.py)."""
from __future__ import annotations

from fastapi import HTTPException
from pydantic import BaseModel, Field

from .. import gaps as store
from ..i18n import tr
from ..music import ConflictError, EpisodeMusic
from ..music_assist import fill_gaps, snap
from ..library import available_to
from .library import asset_or_404, library_of


class AddBody(BaseModel):
    voice_s: float = Field(ge=0, description="point on the voice cut (seconds), as on the editing timeline")
    len_s: float = Field(store.DEFAULT_S, ge=store.MIN_S, le=store.MAX_S)
    snap: bool = Field(True, description="move to the nearest pause between sentences")


class PlaceBody(BaseModel):
    asset_id: str | None = Field(None, max_length=80)
    pid: str | None = Field(None, max_length=40, description="a placed piece of music, moved into the gap")


class LenBody(BaseModel):
    len_s: float = Field(ge=store.MIN_S, le=store.MAX_S)


def register(app, ctx) -> None:
    library = library_of(ctx)

    def music(episode_id: str) -> EpisodeMusic:
        return EpisodeMusic(ctx.ws, ctx.get(episode_id), library)

    def view(m: EpisodeMusic, **extra) -> dict:
        lay = m.layout()
        sr = m.ep.sr
        return {"gaps": m.gaps_json(lay),
                "inserts": [[round(T / sr, 4), round(n / sr, 4)] for T, _, n in lay.inserts if n > 0], **extra}

    @app.get("/api/episodes/{episode_id}/gaps")
    def gaps_view(episode_id: str):
        return view(music(episode_id))

    @app.post("/api/episodes/{episode_id}/gaps")
    def gap_add(episode_id: str, body: AddBody):
        m = music(episode_id)
        at = snap(m, body.voice_s) if body.snap else body.voice_s
        try:
            g = store.add(m.ep, m._voice_to_base(at), body.len_s)
        except ValueError:
            raise HTTPException(409, tr("这里已经有一个间隙了"))
        return view(m, gap_id=g["id"])

    @app.patch("/api/episodes/{episode_id}/gaps/{gap_id}")
    def gap_update(episode_id: str, gap_id: str, body: LenBody):
        m = music(episode_id)
        try:
            store.update(m.ep, gap_id, body.len_s)
        except KeyError:
            raise HTTPException(404, "no such gap")
        return view(m)

    @app.delete("/api/episodes/{episode_id}/gaps/{gap_id}")
    def gap_remove(episode_id: str, gap_id: str):
        m = music(episode_id)
        try:
            store.remove(m.ep, gap_id)
        except KeyError:
            raise HTTPException(404, "no such gap")
        gone = m.drop_gap_music(gap_id)
        return view(m, removed_music=len(gone))

    @app.post("/api/episodes/{episode_id}/music/gaps/auto")
    def gaps_fill(episode_id: str):
        m = music(episode_id)
        out = fill_gaps(m)
        return m.summary() | {"message": out["message"]}

    @app.post("/api/episodes/{episode_id}/music/gaps/place")
    def gaps_place(episode_id: str, body: PlaceBody):
        """「放到 → 间隙」: into the first gap without music (left to right)."""
        m = music(episode_id)
        if not body.asset_id and not body.pid:
            raise HTTPException(422, "asset_id or pid is required")
        if body.asset_id:
            if not available_to(asset_or_404(library, body.asset_id), episode_id):
                raise HTTPException(422, tr("这个素材属于别的剧集。先在素材库把它设为公共或加到这一集。"))
        try:
            p = m.put_in_gap(body.asset_id, body.pid)
        except ConflictError as e:
            raise HTTPException(409, str(e))
        except KeyError:
            raise HTTPException(404, "no such placement")
        return m.summary() | {"placed": p["id"]}
