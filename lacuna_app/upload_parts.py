"""Big files sent in pieces (decision cloud-deploy).

Cloudflare, in front of the shared server, refuses a request body over 100 MB, and a raw track is
1-2 GB. So the browser sends a big file as numbered pieces to ``POST /api/uploads/parts`` (each well
under that limit), into ``<workspace>/tmp/uploads/<id>.part``; then it calls the usual upload endpoint
(import track, library asset) with ``part=<id>`` and an empty body, and that endpoint reads the
assembled file instead of the request body (``source``). A piece sent again (a retry after a dropped
connection) replaces what was there from its offset on. Pieces nobody touched for an hour are pruned.
The file is written off the event loop, and an endpoint that keeps the whole file moves it into place
(``take``) instead of copying it, so a big upload never stalls everyone else's requests. Uploads under way
count as work in progress (``active``): the cloud updater waits for them before a restart.
"""
from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path
from typing import AsyncIterator

from starlette.concurrency import run_in_threadpool

from .store import Workspace

PARTS_DIR = ("tmp", "uploads")
MAX_PIECE = 64 * 1024 ** 2        # the browser sends 32 MB; Cloudflare's limit is 100 MB
MAX_TOTAL = 8 * 1024 ** 3
STALE_S = 3600
READ = 1024 ** 2
FLUSH = 4 * 1024 ** 2               # write to disk in 4 MB steps, each in a worker thread
LIVE_S = 120                        # an upload whose last piece arrived this recently is under way
_ID = re.compile(r"^[0-9a-f]{32}$")
_live: dict[str, float] = {}
_live_lock = threading.Lock()


def _touch(part_id: str, now: float | None = None) -> None:
    with _live_lock:
        _live[part_id] = time.time() if now is None else now


def _done(part_id: str) -> None:
    with _live_lock:
        _live.pop(part_id, None)


def active(now: float | None = None) -> int:
    """Uploads (in pieces) whose last piece arrived within LIVE_S, on any show of this server."""
    now = time.time() if now is None else now
    with _live_lock:
        for k in [k for k, t in _live.items() if now - t > STALE_S]:
            del _live[k]
        return sum(1 for t in _live.values() if now - t <= LIVE_S)


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
    _touch(part_id)
    buf = bytearray()
    with p.open("r+b") as f:
        f.seek(offset)
        f.truncate()
        async for chunk in chunks:
            n += len(chunk)
            if n > MAX_PIECE or offset + n > MAX_TOTAL:
                raise PartError("piece too big")
            buf += chunk
            if len(buf) >= FLUSH:
                await run_in_threadpool(f.write, bytes(buf))
                buf.clear()
        if buf:
            await run_in_threadpool(f.write, bytes(buf))
    _touch(part_id)
    return offset + n


def take(ws: Workspace, part_id: str, target: Path, max_size: int | None = None) -> int:
    """Move the finished file to `target` (same disk: a rename, not a copy); returns its size."""
    p = part_path(ws, part_id)
    _done(part_id)
    if not p.exists():
        raise PartError("unknown upload")
    size = p.stat().st_size
    if max_size is not None and size > max_size:
        p.unlink(missing_ok=True)
        raise PartError("too big")
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(p, target)
    return size


async def source(request, ws: Workspace, part_id: str | None) -> AsyncIterator[bytes]:
    """The upload's bytes: the request body, or (with `part_id`) the pieces sent before, which are
    deleted once read."""
    if not part_id:
        async for chunk in request.stream():
            yield chunk
        return
    p = part_path(ws, part_id)
    _done(part_id)
    if not p.exists():
        raise PartError("unknown upload")
    try:
        with p.open("rb") as f:
            while chunk := f.read(READ):
                yield chunk
    finally:
        p.unlink(missing_ok=True)
