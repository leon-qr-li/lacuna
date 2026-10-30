"""一键修复曲名和作者 (decision 2026-10-30-credit-fix): look up the credits of an episode's own music, or of
the library's shared music, in one go; the editor ticks which answers to keep."""
from __future__ import annotations

from fastapi import HTTPException
from pydantic import BaseModel, Field

from ..credit_fix import CreditFixBusy, CreditFixer
from ..i18n import tr
from ..store import PathError, check_id
from .library import library_of


class FixBody(BaseModel):
    episode: str | None = Field(None, max_length=120)
    prompt: str = Field("", max_length=500, description="where the music comes from, e.g. 全是《午夜凶铃》原声")  # i18n-ignore
    redo: bool = False


class Pick(BaseModel):
    asset_id: str = Field(max_length=80)
    credit: dict


class ApplyBody(BaseModel):
    episode: str | None = Field(None, max_length=120)
    picks: list[Pick] = Field(default_factory=list, max_length=100)


def register(app, ctx) -> None:
    client = ctx.option("credit_fix_client") or ctx.option("credit_client")
    fixer = ctx.provide("credit_fixer", lambda: CreditFixer(library_of(ctx), client=client))
    if fixer.on_usage is None:
        fixer.on_usage = lambda key, u: ctx.log_usage(f"library:{key}", u)

    def episode_or_none(episode: str | None) -> str | None:
        if not episode:
            return None
        try:
            check_id(episode)
        except (PathError, ValueError):
            raise HTTPException(400, "invalid episode id")
        if episode not in ctx.ws.episode_ids():
            raise HTTPException(404, tr("这一集不存在，可能已经删除了"))
        return episode

    @app.get("/api/library/credit-fix")
    def credit_fix_view(episode: str = ""):
        return fixer.view(episode_or_none(episode))

    @app.post("/api/library/credit-fix")
    def credit_fix_start(body: FixBody):
        ep = episode_or_none(body.episode)
        try:
            return fixer.start(ep, body.prompt, body.redo)
        except CreditFixBusy as e:
            raise HTTPException(409, str(e))
        except ValueError as e:
            raise HTTPException(422, str(e))

    @app.post("/api/library/credit-fix/apply")
    def credit_fix_apply(body: ApplyBody):
        ep = episode_or_none(body.episode)
        try:
            n = fixer.apply(ep, [p.model_dump() for p in body.picks])
        except CreditFixBusy as e:
            raise HTTPException(409, str(e))
        return fixer.view(ep) | {"applied": n}

    @app.delete("/api/library/credit-fix")
    def credit_fix_discard(episode: str = ""):
        ep = episode_or_none(episode)
        try:
            fixer.discard(ep)
        except CreditFixBusy as e:
            raise HTTPException(409, str(e))
        return fixer.view(ep)
