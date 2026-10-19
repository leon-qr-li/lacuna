"""/api/staging: whether this server is the staging site (decision staging-site), for the top-bar mark.
Its own cheap route, so every page load doesn't pay for the whole /api/app."""
from __future__ import annotations

from .. import cloud


def register(app, ctx) -> None:
    @app.get("/api/staging")
    def staging():
        return {"staging": cloud.staging()}
