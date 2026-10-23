"""Several people in one episode (lacuna_app/coedit.py): who else is here, the version to refresh to, and
the 409 a stale save gets."""
from __future__ import annotations

from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .. import coedit


class HelloBody(BaseModel):
    leaving: bool = False


def register(app, ctx) -> None:
    presence = ctx.provide("presence", lambda: coedit.Presence())

    @app.exception_handler(coedit.StaleError)
    async def _stale(_req, exc: coedit.StaleError):
        return JSONResponse({"detail": str(exc), "stale": True}, status_code=409)

    @app.post("/api/episodes/{episode_id}/presence")
    def hello(episode_id: str, body: HelloBody):
        """Every few seconds while the episode is open: the others here, and the version to compare with."""
        ep = ctx.peek(episode_id)
        if body.leaving:
            presence.bye(episode_id, coedit.current())
            return {"rev": ep.rev, "others": []}
        return {"rev": ep.rev, "others": presence.hello(episode_id, coedit.current())}
