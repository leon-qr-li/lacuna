"""Learning from review (phase 5, D27/D39): candidate rules Leon approves, incl. asks from the chat."""
from __future__ import annotations

from fastapi import HTTPException
from pydantic import BaseModel, Field

from ..chat_learning import ChatLearner
from ..exporter import Exporter
from ..learning import Learning


class RuleBody(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    action: str = Field(pattern="^(approve|reject|reset)$")


def register(app, ctx) -> None:
    learning = ctx.provide("learning", lambda: Learning(ctx.ws))
    chat_learner = ctx.provide("chat_learner", lambda: ChatLearner(ctx.ws, log_usage=ctx.log_usage))
    exporter = ctx.provide("exporter", lambda: Exporter(ctx.ws))
    exporter.on_done.append(chat_learner.after_export)   # long-term asks are read once an episode is out

    @app.get("/api/learning")
    def learning_overview():
        return learning.overview(ctx.open_episodes())

    @app.post("/api/learning/rules")
    def learning_decide(body: RuleBody):
        try:
            return learning.decide(body.id, body.action, ctx.open_episodes())
        except KeyError:
            raise HTTPException(404, "no such rule")
