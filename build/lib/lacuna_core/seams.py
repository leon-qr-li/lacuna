"""Seam quality checks: find edit points on a timeline and score rendered audio for clicks."""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from .edl import Timeline
from .render import _contiguous


@dataclass(frozen=True)
class Seam:
    track: str
    t: int           # timeline sample of the edit point
    kind: str        # "join" (clip->clip), "in" (gap->clip), "out" (clip->gap)


@dataclass
class SeamReport:
    track: str
    t: int
    kind: str
    delta_ratio: float   # max |x[n]-x[n-1]| at the seam / 99th pct of the surroundings
    hf_ratio: float      # 2nd-difference energy at the seam / median of surrounding windows
    click: bool

    def to_dict(self) -> dict:
        return asdict(self)


def seams(tl: Timeline) -> list[Seam]:
    out = []
    for tr in tl.tracks:
        cl = tr.clips
        for i, c in enumerate(cl):
            prev = cl[i - 1] if i else None
            if prev is not None and prev.end == c.start:
                if not (_contiguous(prev, c) and prev.gain_db == c.gain_db):
                    out.append(Seam(tr.name, c.start, "join"))
            else:
                out.append(Seam(tr.name, c.start, "in"))
            nxt = cl[i + 1] if i + 1 < len(cl) else None
            if nxt is None or nxt.start != c.end:
                out.append(Seam(tr.name, c.end, "out"))
    return sorted(out, key=lambda s: (s.t, s.track))


def check_seam(x: np.ndarray, t: int, sr: int, win_ms: float = 1.0, ctx_ms: float = 60.0,
               delta_thresh: float = 2.5, hf_thresh: float = 8.0) -> tuple[float, float, bool]:
    """Score a seam at index t of mono signal x (timeline-relative).

    A click is a sample-step or HF burst that is large relative to the material on both
    sides. Both ratios must exceed their threshold (speech onsets alone usually raise only
    one of them)."""
    w = max(1, int(win_ms * sr / 1000))
    c = int(ctx_ms * sr / 1000)
    a, b = max(t - c, 2), min(t + c, len(x))
    if b - a < 4 * w:
        return 0.0, 0.0, False
    seg = np.asarray(x[a:b], dtype=np.float64)
    d1 = np.abs(np.diff(seg))
    d2 = np.diff(seg, 2) ** 2
    k = t - a
    near = slice(max(k - w, 0), k + w)
    mask = np.ones(len(d1), bool)
    mask[max(k - 3 * w, 0):k + 3 * w] = False
    floor = 1e-4                       # about -80 dBFS: ratios against digital silence are meaningless
    ref = np.percentile(d1[mask], 99) if mask.any() else floor
    delta_ratio = float(d1[near].max(initial=0.0) / max(ref, floor))
    nwin = len(d2) // (2 * w)
    wins = d2[:nwin * 2 * w].reshape(nwin, 2 * w).sum(axis=1)
    centre = d2[max(k - w, 0):k + w].sum()
    hf_ratio = float(centre / max(np.median(wins), 2 * w * floor ** 2))
    return delta_ratio, hf_ratio, bool(delta_ratio > delta_thresh and hf_ratio > hf_thresh)


def check_seams(audio: np.ndarray, sr: int, seam_list: list[Seam], offset: int = 0,
                **kw) -> list[SeamReport]:
    """`audio` is mono (or (n, ch) -> channel mean) starting at timeline sample `offset`."""
    x = audio if audio.ndim == 1 else audio.mean(axis=1)
    out = []
    for s in seam_list:
        t = s.t - offset
        if 0 <= t < len(x):
            dr, hr, click = check_seam(x, t, sr, **kw)
            out.append(SeamReport(s.track, s.t, s.kind, round(dr, 3), round(hr, 3), click))
    return out
