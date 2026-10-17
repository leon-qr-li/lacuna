"""Music on an episode (phase 6a, D45): placements, ducking, series intro, final-mix stream."""
from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from ..audio import parse_range
from ..music import EpisodeMusic
from .library import asset_or_404, library_of


class PlacementBody(BaseModel):
    asset_id: str | None = Field(None, max_length=40)
    role: str | None = Field(None, pattern="^(intro|interlude|outro|bed|clip)$")
    at_s: float | None = Field(None, ge=0, description="position on the final mix (seconds)")
    until_s: float | None = Field(None, ge=0, description="bed: end on the final mix (seconds)")
    src_in_s: float | None = Field(None, ge=0)
    src_out_s: float | None = Field(None, ge=0)
    overlap_s: float | None = Field(None, ge=0, le=30)
    gain_db: float | None = Field(None, ge=-30, le=12)
    lead_s: float | None = Field(None, ge=0, le=5)
    status: str | None = Field(None, pattern="^(applied|proposed)$")


class SeriesBody(BaseModel):
    name: str = Field("洛城二三事", min_length=1, max_length=80)


def register(app, ctx) -> None:
    library = library_of(ctx)
    musics: dict[str, EpisodeMusic] = {}

    def music(episode_id: str) -> EpisodeMusic:
        ep = ctx.get(episode_id)
        with ctx.lock:
            m = musics.get(episode_id)
            if m is None or m.ep is not ep:
                m = musics[episode_id] = EpisodeMusic(ctx.ws, ep, library)
            return m

    @app.get("/api/episodes/{episode_id}/music")
    def music_view(episode_id: str):
        return music(episode_id).summary()

    def placement_fields(m: EpisodeMusic, body: PlacementBody) -> dict:
        f = body.model_dump(exclude_unset=True)
        for k in ("at_s", "until_s"):     # the UI speaks final-mix time; anchors live on the voice timeline
            if f.get(k) is not None:
                f[k] = m.final_to_voice_s(f[k])
        return f

    @app.post("/api/episodes/{episode_id}/music")
    def music_add(episode_id: str, body: PlacementBody):
        m = music(episode_id)
        if not body.asset_id or not body.role:
            raise HTTPException(422, "asset_id and role are required")
        asset_or_404(library, body.asset_id)
        f = placement_fields(m, body)
        f.pop("asset_id"), f.pop("role")
        m.add(body.asset_id, body.role, **{k: v for k, v in f.items() if v is not None})
        return m.summary()

    @app.patch("/api/episodes/{episode_id}/music/{pid}")
    def music_update(episode_id: str, pid: str, body: PlacementBody):
        m = music(episode_id)
        if body.asset_id:
            asset_or_404(library, body.asset_id)
        try:
            m.update(pid, **placement_fields(m, body))
        except KeyError:
            raise HTTPException(404, "no such placement")
        return m.summary()

    @app.delete("/api/episodes/{episode_id}/music/{pid}")
    def music_remove(episode_id: str, pid: str):
        m = music(episode_id)
        try:
            m.remove(pid)
        except KeyError:
            raise HTTPException(404, "no such placement")
        return m.summary()

    @app.get("/api/episodes/{episode_id}/music/{pid}/preview")
    def music_preview(episode_id: str, pid: str):
        try:
            wav, start = music(episode_id).preview(pid)
        except KeyError:
            raise HTTPException(404, "no such placement")
        return Response(wav, media_type="audio/wav", headers={"Cache-Control": "no-store", "X-Start": str(start)})

    @app.post("/api/episodes/{episode_id}/music/series/apply")
    def music_series_apply(episode_id: str, body: SeriesBody):
        m = music(episode_id)
        m.apply_series(body.name)
        return m.summary()

    @app.post("/api/episodes/{episode_id}/music/series/save")
    def music_series_save(episode_id: str, body: SeriesBody):
        m = music(episode_id)
        m.save_as_series(body.name)
        return m.summary()

    @app.post("/api/episodes/{episode_id}/music/series/dismiss")
    def music_series_dismiss(episode_id: str):
        m = music(episode_id)
        m.dismiss_series()
        return m.summary()

    @app.get("/api/episodes/{episode_id}/mix/{version}.wav")
    def mix_audio(episode_id: str, version: str, request: Request):
        m = music(episode_id)
        enabled = m.ep.enabled
        if version != m.mix_key(enabled):
            raise HTTPException(404, "unknown or expired version")
        total = m.wav_size(enabled)
        rng = parse_range(request.headers.get("range"), total)
        headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"}
        if request.headers.get("range") and rng is None:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{total}"})
        first, last = rng or (0, total - 1)
        headers["Content-Length"] = str(last - first + 1)
        if rng:
            headers["Content-Range"] = f"bytes {first}-{last}/{total}"
        return StreamingResponse(m.iter_wav(enabled, first, last), status_code=206 if rng else 200,
                                 media_type="audio/wav", headers=headers)
