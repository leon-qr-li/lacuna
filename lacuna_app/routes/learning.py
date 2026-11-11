"""Learning from review (phase 5, D27/D39): candidate rules Leon approves, incl. asks from the chat.

The silent after-export chat summary is gone (2026-10-18): asks become rules only through the confirmed
steps in routes/lessons.py."""
from __future__ import annotations

from fastapi import HTTPException
from pydantic import BaseModel, Field

from ..chat_learning import MAX_ASK, remember_text
from ..learning import Learning
from .episodes import remember


class RuleBody(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    action: str = Field(pattern="^(approve|reject|reset|delete)$")


class RememberBody(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    playhead: float = Field(ge=0)


def register(app, ctx) -> None:
    learning = ctx.provide("learning", lambda: Learning(ctx.ws))

    @app.get("/api/learning")
    def learning_overview():
        titles: dict[str, str] = {}

        def eps():
            for ep in ctx.open_episodes():
                titles[ep.id] = ep.meta.get("title") or ep.id
                yield ep
        # the page names a source by its title, not its id (batch 7, B10)
        return learning.overview(eps()) | {"titles": titles}

    @app.post("/api/learning/rules")
    def learning_decide(body: RuleBody):
        try:
            return learning.decide(body.id, body.action, ctx.open_episodes())
        except KeyError:
            raise HTTPException(404, "no such rule")

    @app.post("/api/episodes/{episode_id}/remember")
    def remember_ask(episode_id: str, body: RememberBody):
        """The 「记住」 button: the whole text is the ask (a typed 「记住：」 prefix is dropped); LACUNA
        answers with its reading of it as a draft rule for Leon to confirm (routes/lessons.py)."""
        ask = (remember_text(body.text) or body.text).strip()[:MAX_ASK]
        if not ask:
            raise HTTPException(422, "empty")
        return remember(ctx, ctx.get(episode_id), ask, body.playhead)
