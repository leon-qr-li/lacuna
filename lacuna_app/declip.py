"""Automatic clipping repair of the host recordings (验收 V7).

Leon never cuts a sentence because it clipped; he wants LACUNA to repair what it safely can and
leave the rest. Each host source is scanned once (`lacuna_core.declip.scan`: flattened peaks are
rebuilt, risky ones are left as recorded) and the rebuilt samples are cached next to the episode
in ``<episode>/declip/<key>.npz``. `attach` hangs them on the episode's `MediaRef`s, so review
playback, 整集试听, 配乐, export and every analysis reading through a `SourcePool` hear the repaired
audio, while the recording itself is never written. Episodes imported before this get it the
first time they are opened (a one-off pass of a few seconds per hour of audio); nothing has to
be re-imported. Bumping VERSION re-scans every episode on its next open.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import traceback
from dataclasses import replace
from pathlib import Path

import numpy as np

from lacuna_core import MediaRef, SourcePool, Timeline
from lacuna_core.declip import Patches, scan

from .store import _retry_windows

VERSION = 1
DIR = "declip"

_lock = threading.Lock()


def _path(ep_dir: Path, media_id: str) -> Path:
    return Path(ep_dir) / DIR / (hashlib.sha1(f"{VERSION}|{media_id}".encode()).hexdigest()[:16] + ".npz")


def _load(p: Path) -> tuple[Patches, dict] | None:
    try:
        with np.load(p, allow_pickle=False) as d:
            return Patches.from_npz(d), json.loads(str(d["report"]))
    except (OSError, ValueError, KeyError):
        return None


def _save(p: Path, patches: Patches, report: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=p.name + ".", suffix=".tmp", dir=p.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            np.savez(f, **patches.to_npz(), report=np.array(json.dumps(report)))
            f.flush()
            os.fsync(f.fileno())
        _retry_windows(lambda: os.replace(tmp, p))
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def repair(ep_dir: Path, m: MediaRef) -> tuple[Patches, dict]:
    """The repair of one source: cached, or scanned now (and cached)."""
    p = _path(ep_dir, m.media_id)
    with _lock:
        hit = _load(p) if p.is_file() else None
        if hit is not None:
            return hit
        with SourcePool({m.media_id: m}, repaired=False) as pool:
            patches, rep = scan(lambda a, b: pool.read(m.media_id, a, b), m.frames, m.sample_rate)
        report = rep.to_dict(m.sample_rate)
        _save(p, patches, report)
        return patches, report


def voice_media(base: Timeline) -> list[str]:
    """The sources the host tracks play (music is never on the voice timeline)."""
    return sorted({c.media_id for t in base.tracks for c in t.clips})


def attach(ep_dir: Path, media: dict[str, MediaRef], base: Timeline) -> dict[str, MediaRef]:
    """`media` with each host source's repair attached. A failure only leaves that source as
    recorded: opening an episode never fails because of the repair."""
    out = dict(media)
    for mid in voice_media(base):
        m = media.get(mid)
        if m is None:
            continue
        try:
            patches, _ = repair(ep_dir, m)
        except Exception:   # unreadable source, disk full ...: play it as recorded
            traceback.print_exc()
            continue
        out[mid] = replace(m, patches=patches if len(patches) else None)
    return out


def track_report(ep_dir: Path, media: dict[str, MediaRef], base: Timeline, track: str) -> dict:
    """What the repair did on one host track, in base-timeline seconds."""
    sr = base.sample_rate
    events, skipped, repaired = [], [], 0
    for c in base.track(track).clips:
        m = media.get(c.media_id)
        if m is None:
            continue
        try:
            _, rep = repair(ep_dir, m)
        except Exception:
            traceback.print_exc()
            continue
        to_base = lambda s: (c.start + (int(round(s * sr)) - c.src_in)) / sr   # noqa: E731
        inside = lambda s: c.src_in <= int(round(s * sr)) < c.src_out           # noqa: E731
        ev = [s for s in rep.get("event_at", []) if inside(s)]
        sk = [s for s in rep.get("skipped_at", []) if inside(s)]
        events += [to_base(s) for s in ev]
        skipped += [to_base(s) for s in sk]
        repaired += len(ev) - len(sk)
    return {"events": len(events), "repaired": repaired, "skipped_times": sorted(skipped)}
