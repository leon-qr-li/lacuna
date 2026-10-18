"""Confirmed learning (首次检测 #9, #12): 「记住」 drafts in the chat and the 本集学到的规则 step."""
from __future__ import annotations

from fastapi import HTTPException
from pydantic import BaseModel, Field

from ..chat_learning import ChatAsks
from ..learning import Learning
from ..lessons import ClaudeRuleWriter, Lessons


class ActionBody(BaseModel):
    action: str = Field(pattern="^(confirm|drop|adopt|skip|reopen)$")


class TextBody(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


def register(app, ctx) -> None:
    learning = ctx.provide("learning", lambda: Learning(ctx.ws))
    asks = ctx.provide("chat_asks", lambda: ChatAsks(ctx.ws))
    writer = ctx.provide("rule_writer", ClaudeRuleWriter)
    lessons = ctx.provide("lessons", lambda: Lessons(ctx.ws, learning, asks, writer, ctx.log_usage))

    def guard(fn):
        try:
            return fn()
        except KeyError:
            raise HTTPException(404, "not found")
        except ValueError as e:
            raise HTTPException(409, str(e))

    @app.post("/api/episodes/{episode_id}/remember/{did}")
    def remember_decide(episode_id: str, did: str, body: ActionBody):
        return guard(lambda: lessons.decide_draft(ctx.get(episode_id), did, body.action))

    @app.post("/api/episodes/{episode_id}/remember/{did}/revise")
    def remember_revise(episode_id: str, did: str, body: TextBody):
        return guard(lambda: lessons.revise_draft(ctx.get(episode_id), did, body.text))

    @app.get("/api/episodes/{episode_id}/lessons")
    def lessons_view(episode_id: str):
        return lessons.view(ctx.get(episode_id))

    @app.post("/api/episodes/{episode_id}/lessons/run")
    def lessons_run(episode_id: str):
        return lessons.start(ctx.get(episode_id))

    @app.post("/api/episodes/{episode_id}/lessons/{lid}")
    def lessons_decide(episode_id: str, lid: str, body: ActionBody):
        return guard(lambda: lessons.decide_lesson(ctx.get(episode_id), lid, body.action))

    @app.post("/api/episodes/{episode_id}/lessons/{lid}/edit")
    def lessons_edit(episode_id: str, lid: str, body: TextBody):
        return guard(lambda: lessons.edit_lesson(ctx.get(episode_id), lid, body.text))

    @app.post("/api/episodes/{episode_id}/lessons/{lid}/revise")
    def lessons_revise(episode_id: str, lid: str, body: TextBody):
        return guard(lambda: lessons.revise_lesson(ctx.get(episode_id), lid, body.text))
