"""Streaming, sample-accurate renderer for a per-track `Timeline`.

Every clip edge that is a real seam gets a short crossfade centred on the edit point, using
source "handles" beyond the clip's in/out points (equal-power when the two sides are
different material, equal-gain when they are the same contiguous source with only a gain
change). Edges where the neighbour continues the same source exactly are not seams.

Output at sample t depends only on the timeline and settings, never on chunking, so a range
render is bit-identical to the same samples of a full render (this is what makes segment
caching for previews safe). Memory is O(chunk): sources are read by seek per chunk.
"""
from __future__ import annotations

import bisect
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from .edl import Timeline, Track, canonical_json
from .media import SourcePool

POWER, LINEAR = "p", "l"


@dataclass(frozen=True)
class RenderSettings:
    xfade_ms: float = 16.0
    channels: int = 1               # 1 = mono sum, 2 = constant-power panned stereo
    ceiling_db: float = -1.0        # soft-clip knee (peak safety) ...
    limit_db: float = -0.1          # ... asymptote: output never exceeds this
    chunk_s: float = 5.0

    def xfade(self, sr: int) -> int:
        return int(round(self.xfade_ms * sr / 1000))


@dataclass(frozen=True)
class ClipPlan:
    """What the renderer does for one clip: audible span [t0, t1) on the timeline, the source
    sample that plays at t0, gain and the in/out ramps (start, length, curve)."""
    t0: int
    t1: int
    media_id: str
    src_at_t0: int
    gain: float
    ramp_in: tuple[int, int, str] | None
    ramp_out: tuple[int, int, str] | None


@dataclass
class RenderStats:
    samples: int = 0
    peak: float = 0.0               # before peak safety
    limited: int = 0                # samples touched by the soft clipper


def _contiguous(a, b) -> bool:
    return a.end == b.start and a.media_id == b.media_id and a.src_out == b.src_in


def plan_track(track: Track, xfade: int, frames: dict[str, int]) -> list[ClipPlan]:
    """Resolve fades/handles for every clip on one track (sorted by t0)."""
    h = xfade // 2
    clips = track.clips
    plans = []
    for i, c in enumerate(clips):
        prev = clips[i - 1] if i > 0 else None
        nxt = clips[i + 1] if i + 1 < len(clips) else None
        n_src = frames[c.media_id]
        t0, t1 = c.start, c.end
        ramp_in = ramp_out = None
        # ---- in edge
        if c.fade_in:
            ramp_in = (c.start, c.fade_in, POWER)
        elif xfade and not (prev and _contiguous(prev, c) and prev.gain_db == c.gain_db):
            curve = LINEAR if prev and _contiguous(prev, c) else POWER
            pre = min(h, c.src_in)                    # handle available in the source
            if prev is not None and prev.end != c.start:
                pre = min(pre, c.start - prev.end)    # never reach back past a gap
            t0 = c.start - pre
            ramp_in = (t0, xfade, curve)
        # ---- out edge
        if c.fade_out:
            ramp_out = (c.end - c.fade_out, c.fade_out, POWER)
        elif xfade and not (nxt and _contiguous(c, nxt) and nxt.gain_db == c.gain_db):
            curve = LINEAR if nxt and _contiguous(c, nxt) else POWER
            post = min(xfade - h, n_src - c.src_out)
            if nxt is not None and nxt.start != c.end:
                post = min(post, nxt.start - c.end)
            t1 = c.end + post
            ramp_out = (t1 - xfade, xfade, curve)
        plans.append(ClipPlan(t0, t1, c.media_id, c.src_in - (c.start - t0),
                              10 ** (c.gain_db / 20), ramp_in, ramp_out))
    return plans


def _plan_in_range(p: ClipPlan, a: int, b: int) -> tuple:
    """The part of a plan that affects samples [a, b), relative to a (for cache keys).
    Ramps entirely outside the range evaluate to exactly 1.0 there and are dropped."""
    s, e = max(p.t0, a), min(p.t1, b)
    ramps = [r and (r[0] - a, *r[1:]) if r and r[0] < e and r[0] + r[1] > s else None
             for r in (p.ramp_in, p.ramp_out)]
    return (s - a, e - a, p.media_id, p.src_at_t0 + (s - p.t0), p.gain, *ramps)


def _ramp(t: np.ndarray, r: tuple[int, int, str], rising: bool) -> np.ndarray:
    start, n, curve = r
    x = np.clip((t - start + 0.5) / n, 0.0, 1.0)
    if not rising:
        x = 1.0 - x
    return x if curve == LINEAR else np.sin(0.5 * np.pi * x)


def _duck_db(track: Track, t: np.ndarray) -> np.ndarray:
    db = np.full(len(t), track.gain_db, dtype=np.float64)
    for d in track.ducks:
        if d.ramp:
            w = np.clip(np.minimum(t - (d.start - d.ramp), (d.end + d.ramp) - t) / d.ramp, 0, 1)
        else:
            w = ((t >= d.start) & (t < d.end)).astype(np.float64)
        db -= d.depth_db * w
    return db


class Renderer:
    def __init__(self, pool: SourcePool, settings: RenderSettings = RenderSettings()):
        self.pool = pool
        self.settings = settings
        self._plans: dict[tuple, list[list[ClipPlan]]] = {}
        self._loops: dict[tuple, np.ndarray] = {}

    # ---------------------------------------------------------------- planning
    def plans(self, tl: Timeline) -> list[list[ClipPlan]]:
        key = (tl.digest(), self.settings.xfade_ms)
        p = self._plans.get(key)
        if p is None:
            frames = {k: m.frames for k, m in self.pool.media.items()}
            x = self.settings.xfade(tl.sample_rate)
            p = [plan_track(tr, x, frames) for tr in tl.tracks]
            if len(self._plans) > 32:
                self._plans.clear()
            self._plans[key] = p
        return p

    def _room_loop(self, rt, xfade: int) -> np.ndarray:
        key = (rt.media_id, rt.src_in, rt.src_out, xfade)
        loop = self._loops.get(key)
        if loop is None:
            buf = self.pool.read(rt.media_id, rt.src_in, rt.src_out).astype(np.float64)
            x = max(1, min(xfade * 4, len(buf) // 4))
            n = len(buf) - x
            loop = buf[:n].copy()
            w = np.sin(0.5 * np.pi * (np.arange(x) + 0.5) / x)
            loop[:x] = buf[:x] * w + buf[n:] * np.sqrt(1 - w ** 2)   # seamless wrap
            self._loops[key] = loop
        return loop

    # ---------------------------------------------------------------- rendering
    def render_track(self, tl: Timeline, i: int, a: int, b: int) -> np.ndarray:
        tr = tl.tracks[i]
        out = np.zeros(b - a, dtype=np.float64)
        if tr.mute:
            return out
        t = np.arange(a, b, dtype=np.float64)
        plans = self.plans(tl)[i]
        cover = np.zeros(b - a, dtype=np.float64) if tr.room_tone else None
        x = self.settings.xfade(tl.sample_rate)
        t1max = np.maximum.accumulate([p.t1 for p in plans]) if plans else []
        lo = bisect.bisect_right(t1max, a)        # every plan before lo ends at or before a
        for p in plans[lo:]:
            if p.t0 >= b:
                break
            s, e = max(p.t0, a), min(p.t1, b)
            if e <= s:
                continue
            tt = t[s - a:e - a]
            env = np.ones(e - s)
            for r, rising in ((p.ramp_in, True), (p.ramp_out, False)):
                if r:   # a ramp is exactly 1.0 outside its own span within the plan
                    rs, re_ = max(r[0], s) - s, min(r[0] + r[1], e) - s
                    if re_ > rs:
                        env[rs:re_] *= _ramp(tt[rs:re_], r, rising)
            src = self.pool.read(p.media_id, p.src_at_t0 + (s - p.t0), p.src_at_t0 + (e - p.t0))
            out[s - a:e - a] += src * (env * p.gain)
            if cover is not None:
                cover[s - a:e - a] += env ** 2
        if cover is not None and plans:
            rt = tr.room_tone
            loop = self._room_loop(rt, x)
            fill = np.sqrt(np.clip(1.0 - cover, 0.0, 1.0))
            inner = (t >= plans[0].t1 - x) & (t < plans[-1].t0 + x)   # interior gaps only
            fill[~inner] = 0.0
            if fill.any():
                out += loop[np.arange(a, b) % len(loop)] * fill * 10 ** (rt.gain_db / 20)
        return out * 10 ** (_duck_db(tr, t) / 20)

    def render(self, tl: Timeline, a: int, b: int, stats: RenderStats | None = None) -> np.ndarray:
        """Mixed float32 samples for timeline [a, b), shape (n, channels)."""
        ch = self.settings.channels
        mix = np.zeros((b - a, ch), dtype=np.float64)
        for i, tr in enumerate(tl.tracks):
            y = self.render_track(tl, i, a, b)
            if ch == 1:
                mix[:, 0] += y
            else:
                th = (np.clip(tr.pan, -1, 1) + 1) * np.pi / 4
                mix[:, 0] += y * np.cos(th)
                mix[:, 1] += y * np.sin(th)
        return self._peak_safety(mix, stats).astype(np.float32)

    def _peak_safety(self, x: np.ndarray, stats: RenderStats | None) -> np.ndarray:
        c = 10 ** (self.settings.ceiling_db / 20)
        mag = np.abs(x)
        over = mag > c
        if stats is not None:
            stats.samples += len(x)
            stats.peak = max(stats.peak, float(mag.max(initial=0.0)))
            stats.limited += int(over.any(axis=1).sum())
        if over.any():
            k = max(10 ** (self.settings.limit_db / 20) - c, 1e-6)
            x = np.where(over, np.sign(x) * (c + k * np.tanh((mag - c) / k)), x)
        return x

    def iter_chunks(self, tl: Timeline, a: int = 0, b: int | None = None,
                    stats: RenderStats | None = None):
        b = tl.length if b is None else b
        step = max(1, int(self.settings.chunk_s * tl.sample_rate))
        for s in range(a, b, step):
            yield self.render(tl, s, min(s + step, b), stats)

    def render_to_file(self, tl: Timeline, path: str | Path, a: int = 0, b: int | None = None,
                       subtype: str = "PCM_24") -> RenderStats:
        """Stream a render to WAV; written to a temp file and atomically renamed."""
        path = Path(path)
        tmp = path.with_name(path.name + ".part")
        stats = RenderStats()
        with sf.SoundFile(str(tmp), "w", tl.sample_rate, self.settings.channels,
                          subtype=subtype, format="WAV") as f:
            for chunk in self.iter_chunks(tl, a, b, stats):
                f.write(chunk)
        os.replace(tmp, path)
        return stats

    # ---------------------------------------------------------------- cache keys
    def range_key(self, tl: Timeline, a: int, b: int) -> str:
        """Hash of everything that influences output samples [a, b), expressed relative to a.

        Built from the same plans the renderer uses, so any upstream timing change that moves
        material into/out of/within the range changes the key, while unrelated edits (or a
        pure shift of identical content to a new absolute position, except for room-tone
        phase) do not."""
        parts: list = [self.settings.xfade_ms, self.settings.channels, self.settings.ceiling_db,
                       self.settings.limit_db,
                       tl.sample_rate, b - a]
        x = self.settings.xfade(tl.sample_rate)
        for tr, plans in zip(tl.tracks, self.plans(tl)):
            items = [_plan_in_range(p, a, b) for p in plans if p.t0 < b and p.t1 > a]
            ducks = [(d.start - a, d.end - a, d.depth_db, d.ramp) for d in tr.ducks
                     if d.start - d.ramp < b and d.end + d.ramp > a]
            room = None
            if tr.room_tone and plans:
                rt = tr.room_tone
                loop_len = len(self._room_loop(rt, x))
                n = b - a
                lo = min(max(plans[0].t1 - x - a, 0), n)
                hi = min(max(plans[-1].t0 + x - a, 0), n)
                room = (rt.media_id, rt.src_in, rt.src_out, rt.gain_db, a % loop_len, lo, hi)
            repair = sorted({k for it in items if (k := self.pool.patch_key(it[2]))})
            parts.append((tr.name, tr.gain_db, tr.pan, tr.mute, items, ducks, room) + ((repair,) if repair else ()))
        return hashlib.sha256(canonical_json(parts).encode()).hexdigest()
