"""Automatic clipping (破音) repair of the hosts' recordings (decision 2026-10-18-auto-declip).

Each host recording is scanned once (`lacuna_core.declip.scan`: flat runs at the source's own peak,
short ones restored by AR interpolation, long or risky ones left alone). The result is a small set of
patches cached in ``<episode>/declip/<media>.npz`` and in memory, and every pool that renders the
episode for listening or export (`pool_for`) applies them as it reads. The recordings themselves are
never written. Analysis code (transcription, AI cut, room tone) keeps reading the raw files.
"""
from __future__ import annotations

import os
import tempfile
import threading
import traceback
from collections import OrderedDict
from pathlib import Path

from lacuna_core import MediaRef, SourcePool
from lacuna_core.declip import VERSION, Repair, scan

DIR = "declip"

_lock = threading.Lock()
_mem: OrderedDict[tuple[str, int], Repair] = OrderedDict()
_scanning: dict[tuple[str, int], threading.Event] = {}


def voice_media(ep) -> list[str]:
    """Media ids of the host recordings (what the base timeline's clips play)."""
    seen: dict[str, None] = {}
    for t in ep.base.tracks:
        for c in t.clips:
            seen.setdefault(c.media_id, None)
    return list(seen)


def _file(ep, media_id: str) -> Path:
    return ep.dir / DIR / f"v{VERSION}_{media_id.split(':')[-1][:40]}.npz"


def _write(path: Path, data: bytes, protected: tuple[str, ...]) -> None:
    if any(Path(p).resolve() == path.resolve() for p in protected):
        raise PermissionError("refusing to write over source media")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _cached(ep, media_id: str) -> Repair | None:
    """From memory or the episode's cache file; None when it has not been scanned yet."""
    key = (media_id, VERSION)
    with _lock:
        hit = _mem.get(key)
        if hit is not None:
            _mem.move_to_end(key)
            return hit
    try:
        path = _file(ep, media_id)
        r = Repair.from_bytes(path.read_bytes()) if path.is_file() else None
    except (OSError, ValueError, KeyError):
        r = None
    if r is not None:
        _remember(key, r)
    return r


def _remember(key: tuple[str, int], r: Repair) -> None:
    with _lock:
        _mem[key] = r
        while len(_mem) > 16:
            _mem.popitem(last=False)


def repair_for(ep, media_id: str) -> Repair | None:
    """The repair of one recording: from memory, the episode's cache file, or a scan (once; a
    second caller waits for the scan already running). None (then an empty repair) if the
    recording can't be read."""
    r = _cached(ep, media_id)
    if r is not None:
        return r
    key = (media_id, VERSION)
    with _lock:
        ev = _scanning.get(key)
        mine = ev is None
        if mine:
            ev = _scanning[key] = threading.Event()
    if not mine:
        ev.wait()
        return repair_for(ep, media_id)
    try:
        m: MediaRef = ep.media[media_id]
        try:
            with SourcePool({media_id: m}) as pool:
                r = scan(lambda a, b: pool.read(media_id, a, b), m.frames, m.sample_rate)
        except Exception:     # noqa: BLE001 - an unreadable source just plays as it is (until restart)
            traceback.print_exc()
            _remember(key, Repair(m.sample_rate))
            return None
        try:
            _write(_file(ep, media_id), r.to_bytes(), tuple(x.path for x in ep.media.values()))
        except OSError:
            traceback.print_exc()
        _remember(key, r)
        return r
    finally:
        with _lock:
            _scanning.pop(key, None)
        ev.set()


def repairs(ep, wait: bool = True, on_ready=None) -> dict[str, Repair]:
    """Repairs of the host recordings that change anything. With wait=False only what is already
    known is returned and the rest is scanned in the background; `on_ready(all repairs)` is called
    when that finishes (playback starts at once and picks the repairs up a few seconds later)."""
    out, missing = {}, []
    for mid in voice_media(ep):
        r = repair_for(ep, mid) if wait else _cached(ep, mid)
        if r is None and not wait:
            missing.append(mid)
        elif r is not None and len(r.starts):
            out[mid] = r
    if missing:
        def run():
            for mid in missing:
                repair_for(ep, mid)
            if on_ready is not None:
                on_ready(repairs(ep))
        threading.Thread(target=run, name=f"declip-{ep.id}", daemon=True).start()
    return out


def pool_for(ep, media: dict[str, MediaRef] | None = None, wait: bool = True) -> SourcePool:
    """A pool over `media` (default: the episode's) that plays the hosts with clipping repaired.
    wait=False (playback): never blocks on a first scan; the repairs join the pool when it is done."""
    pool = SourcePool(ep.media if media is None else media)
    pool.set_repairs(repairs(ep, wait, on_ready=pool.set_repairs))
    return pool
