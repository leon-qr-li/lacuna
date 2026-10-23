"""Big files sent in pieces (decision cloud-deploy).

Cloudflare, in front of the shared server, refuses a request body over 100 MB, and a raw track is
1-2 GB. So the browser sends a big file as numbered pieces to ``POST /api/uploads/parts`` (each well
under that limit), into ``<workspace>/tmp/uploads/<id>.part``; then it calls the usual upload endpoint
(import track, library asset) with ``part=<id>`` and an empty body, and that endpoint reads the
assembled file instead of the request body (``source``). A piece sent again (a retry after a dropped
connection) replaces what was there from its offset on. Pieces nobody finished are pruned after a
day. The desktop app uses the same path for big files; nothing leaves the machine there either.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import AsyncIterator

from .store import Workspace

PARTS_DIR = ("tmp", "uploads")
MAX_PIECE = 64 * 1024 ** 2        # the browser sends 32 MB; Cloudflare's limit is 100 MB
MAX_TOTAL = 8 * 1024 ** 3
STALE_S = 24 * 3600
READ = 1024 ** 2
_ID = re.compile(r"^[0-9a-f]{32}$")


class PartError(ValueError):
    pass


def parts_dir(ws: Workspace) -> Path:
    return ws.root.joinpath(*PARTS_DIR)


def part_path(ws: Workspace, part_id: str) -> Path:
    if not _ID.match(part_id or ""):
        raise PartError("bad upload id")
    return parts_dir(ws) / f"{part_id}.part"


def prune(ws: Workspace, now: float | None = None) -> None:
    now = time.time() if now is None else now
    d = parts_dir(ws)
    if not d.is_dir():
        return
    for p in d.glob("*.part"):
        try:
            if now - p.stat().st_mtime > STALE_S:
                p.unlink()
        except OSError:
            pass


async def write_piece(ws: Workspace, part_id: str, offset: int, chunks: AsyncIterator[bytes]) -> int:
    """Write one piece at `offset` (0 starts a new file); returns the file's size after it."""
    p = part_path(ws, part_id)
    if offset < 0:
        raise PartError("bad offset")
    if offset == 0:
        prune(ws)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"")
    elif not p.exists():
        raise PartError("unknown upload")
    elif offset > p.stat().st_size:
        raise PartError("a piece is missing")
    n = 0
    with p.open("r+b") as f:
        f.seek(offset)
        f.truncate()
        async for chunk in chunks:
            n += len(chunk)
            if n > MAX_PIECE or offset + n > MAX_TOTAL:
                raise PartError("piece too big")
            f.write(chunk)
    return offset + n


async def source(request, ws: Workspace, part_id: str | None) -> AsyncIterator[bytes]:
    """The upload's bytes: the request body, or (with `part_id`) the pieces sent before, which are
    deleted once read."""
    if not part_id:
        async for chunk in request.stream():
            yield chunk
        return
    p = part_path(ws, part_id)
    if not p.exists():
        raise PartError("unknown upload")
    try:
        with p.open("rb") as f:
            while chunk := f.read(READ):
                yield chunk
    finally:
        p.unlink(missing_ok=True)
