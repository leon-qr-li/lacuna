"""App version and settings (phase 7, D51; desktop app retired 2026-10-19, decision desktop-retired).

The version is the `VERSION` file the Docker image writes (the git commit); a development checkout
has none and reports "dev". `/api/app` also lists the work in progress ("busy"), which the cloud
host's updater (deploy/host/lacuna-update) waits on before it swaps in a new image.
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from fastapi import Request
from pydantic import BaseModel, Field

APP_ROOT = Path(__file__).resolve().parent.parent      # the image's /app (or the git checkout)


def current_version(app_root: Path = APP_ROOT) -> str:
    try:
        return (app_root / "VERSION").read_text(encoding="utf-8").strip() or "dev"
    except OSError:
        return "dev"


def release_date(app_root: Path = APP_ROOT) -> str | None:
    """The version people see: the day this build was made ("2026.10.25", from VERSION's time, written at
    docker build). The commit stays in `version` for the admin area and feedback (batch 7, B17)."""
    try:
        return datetime.fromtimestamp((app_root / "VERSION").stat().st_mtime, tz=timezone.utc).strftime("%Y.%m.%d")
    except OSError:
        return None


# ---------------------------------------------------------------------------- environment

def ffmpeg_status() -> dict:
    return {"ffmpeg": shutil.which("ffmpeg"), "ffprobe": shutil.which("ffprobe")}


def platform_name() -> str:
    return {"win32": "Windows", "darwin": "macOS"}.get(sys.platform, sys.platform)


# ---------------------------------------------------------------------------- API

class KeyBody(BaseModel):
    key: str = Field(..., max_length=500)


def register(app, workspace: Path, busy: Callable[[], list[str]],
             key_status: Callable[[], dict], models_ready: Callable[[], bool]) -> None:
    """/api/app*: version + settings."""
    from fastapi import HTTPException

    from . import editor
    from .cloud import LOOPBACK, enabled as cloud_enabled, staging

    def info(server_side: bool) -> dict:
        # on the shared server only the host's updater (loopback) sees the busy list and the folder: they name
        # other people's episodes and the server's paths (batch 8, S2)
        return {"version": current_version(), "release": release_date(), "platform": platform_name(),
                "workspace": str(workspace) if server_side else "",
                "key": key_status(), "models": models_ready(), "busy": busy() if server_side else [],
                "cloud": cloud_enabled(), "staging": staging()} | {
                    # found or not, without where (batch 11, S1)
                    k: v if server_side else (k if v else None) for k, v in ffmpeg_status().items()}

    @app.get("/api/app")
    def app_info(request: Request):
        client = request.client.host if request.client else None
        return info(not cloud_enabled() or client in LOOPBACK)

    @app.post("/api/app/api-key")
    def set_key(body: KeyBody):
        """Development checkout only (the cloud blocks it: keys come from the server's environment).
        The AI clients are made at startup, so the key takes effect after a restart by hand."""
        try:
            where = editor.save_api_key(body.key)
        except ValueError as e:
            raise HTTPException(400, str(e))
        except OSError as e:
            raise HTTPException(500, str(e))
        return {"saved": True, "where": where}
