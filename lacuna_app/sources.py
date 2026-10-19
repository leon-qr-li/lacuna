"""An episode's recordings uploaded again when they are not on the server.

The desktop app reads raw tracks where they lie (D29), e.g. ``C:\\Users\\…\\Downloads\\Leon.wav``. Moving
the desktop workspace to the server (#127) brought the episodes but not those files, so such an episode
opens but nothing in it can be heard (every listen, review clip, music mix, 声音 and export reads them).
The episode page lists what is missing (``Episode.missing_sources``); the owner uploads the original
files, each is matched by its bytes (a recording's media id is the sha256 of its file), kept in
``<episode>/media/`` and the episode points at it. A file that is not one of the missing recordings is
refused; nothing else changes. Decision: docs/decisions/2026-10-19-missing-recordings.md.
"""
from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path
from typing import AsyncIterator

from .import_tracks import safe_name

MEDIA_DIR = "media"


class NotMissing(ValueError):
    """The uploaded file is none of the episode's missing recordings."""


async def receive(ep, name: str, chunks: AsyncIterator[bytes]) -> dict:
    """Store an uploaded recording and point the episode at it; returns the missing entry it filled."""
    missing = {m["media_id"]: m for m in ep.missing_sources()}
    d = ep.dir / MEDIA_DIR
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f".upload-{uuid.uuid4().hex}"
    h = hashlib.sha256()
    try:
        with tmp.open("wb") as f:
            async for chunk in chunks:
                h.update(chunk)
                f.write(chunk)
        media_id = "sha256:" + h.hexdigest()
        if media_id not in missing:
            raise NotMissing(name)
        dst = _free(d, safe_name(name))
        os.replace(tmp, dst)
    finally:
        tmp.unlink(missing_ok=True)
    ep.relink(media_id, dst)
    return missing[media_id]


def _free(d: Path, name: str) -> Path:
    p, stem, suffix, i = d / name, Path(name).stem, Path(name).suffix, 2
    while p.exists():
        p, i = d / f"{stem}_{i}{suffix}", i + 1
    return p
