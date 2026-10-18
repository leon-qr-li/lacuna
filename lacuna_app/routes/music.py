"""Music on an episode (phase 6a, D45): placements, ducking, series intro, final-mix stream."""
from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from ..audio import parse_range
from ..music import EpisodeMusic
from ..music_assist import MusicChat, auto_place
from .library import asset_or_404, library_of


class PlacementBody(BaseModel):
    asset_id: str | None = Field(None, max_length=40)
    role: str | None = Field(None, pattern="^(intro|interlude|outro|bed|clip)$")
    at_s: float | None = Field(None, ge=0, description="position on the final mix (seconds)")
    until_s: float | None = Field(None, ge=0, description="bed: end on the final mix (seconds)")
    src_in_s: float | None = Field(None, ge=0)
    src_out_s: float | None = Field(None, ge=0)
    gain_db: float | None = Field(None, ge=-30, le=12)
    solo_s: float | None = Field(None, ge=0, le=600, description="intro: music alone; interlude: full level in the gap")
    ramp_s: float | None = Field(None, ge=0, le=10, description="rise / fall between full level and background")
    ramp_out_s: float | None = Field(None, ge=0, le=10, description="interlude: fall back to background")
    bg_db: float | None = Field(None, ge=0, le=40, description="background: this much under full level")
    pre_s: float | None = Field(None, ge=0, le=600, description="interlude: plays under the talk before the gap")
    bye_s: float | None = Field(None, ge=0, description="outro: second of the file where the voice ends")
    fade_out_s: float | None = Field(None, ge=0, le=30)
    lead_s: float | None = Field(None, ge=0, le=5)
    status: str | None = Field(None, pattern="^(applied|proposed)$")


class ChatBody(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class DraftMoveBody(BaseModel):
    pid: str = Field(max_length=40)
    voice_s: float = Field(ge=0)


class SeriesBody(BaseModel):
    name: str = Field("洛城二三事", min_length=1, max_length=80)  # i18n-ignore


def register(app, ctx) -> None:
    library = library_of(ctx)
    musics: dict[str, EpisodeMusic] = {}
    chat = ctx.provide("music_chat", lambda: MusicChat(ctx.option("music_client")))

    def music(episode_id: str) -> EpisodeMusic:
        ep = ctx.get(episode_id)
        with ctx.lock:
            m = musics.get(episode_id)
            if m is None or m.ep is not ep:
                m = musics[episode_id] = EpisodeMusic(ctx.ws, ep, library)
            for eid in [e for e in musics if e not in ctx.episodes]:
                del musics[eid]       # rebuilt from music.json when needed; lets closed episodes go
            return m

    @app.get("/api/episodes/{episode_id}/music")
    def music_view(episode_id: str):
        return music(episode_id).summary()

    def placement_fields(m: EpisodeMusic, body: PlacementBody, pid: str | None = None) -> dict:
        f = body.model_dump(exclude_unset=True)
        for k in ("at_s", "until_s"):     # the UI speaks final-mix time; anchors live on the voice timeline
            if f.get(k) is not None:
                f[k] = m.final_to_voice_s(f[k], exclude=pid)
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
            m.update(pid, **placement_fields(m, body, pid))
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

    # ---- suggestions: by use, or from talking to Claude; heard first, applied only when accepted
    @app.post("/api/episodes/{episode_id}/music/auto")
    def music_auto(episode_id: str):
        m = music(episode_id)
        out = auto_place(m)
        return m.summary() | {"message": out["message"]}

    @app.post("/api/episodes/{episode_id}/music/chat")
    def music_chat(episode_id: str, body: ChatBody):
        m = music(episode_id)
        out = chat.ask(m, body.text.strip())
        if out.get("usage"):
            ctx.log_usage(episode_id, {"kind": "music_chat", **out["usage"]})
        return m.summary() | {"message": out["message"]}

    @app.post("/api/episodes/{episode_id}/music/draft/{draft_id}/accept")
    def music_draft_accept(episode_id: str, draft_id: str):
        m = music(episode_id)
        try:
            m.accept_draft(draft_id)
        except KeyError:
            raise HTTPException(404, "no such suggestion")
        return m.summary()

    @app.post("/api/episodes/{episode_id}/music/draft/discard")
    def music_draft_discard(episode_id: str):
        m = music(episode_id)
        m.discard_draft()
        return m.summary()

    @app.post("/api/episodes/{episode_id}/music/draft/move")
    def music_draft_move(episode_id: str, body: DraftMoveBody):
        m = music(episode_id)
        try:
            m.move_draft(body.pid, body.voice_s)
        except KeyError:
            raise HTTPException(404, "no such suggested placement")
        return m.summary()

    @app.get("/api/episodes/{episode_id}/music/draft/{pid}/preview")
    def music_draft_preview(episode_id: str, pid: str):
        m = music(episode_id)
        d = m.draft()
        if not d:
            raise HTTPException(404, "no suggestion")
        try:
            wav, start = m.preview(pid, placements=d["placements"])
        except KeyError:
            raise HTTPException(404, "no such placement in the suggestion")
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
