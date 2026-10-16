"""Cut-point refinement: move a candidate boundary (e.g. an ASR word edge) to the nearest
low-energy valley, then to a nearby zero crossing, within +-radius."""
from __future__ import annotations

from typing import Sequence

import numpy as np

from .media import SourcePool


def snap_cut(signals: Sequence[np.ndarray], center: int, sr: int, radius_ms: float = 150.0,
             frame_ms: float = 10.0, distance_penalty_db: float = 3.0, zc_ms: float = 2.0) -> int:
    """Return the refined index into `signals` (all same length, aligned; e.g. both host tracks).

    Cost per candidate = short-time energy (dB, summed over tracks, `frame_ms` window) plus
    `distance_penalty_db` * |offset| / radius, so a slightly deeper valley far away does not
    beat a good one nearby. The winner is then nudged to the closest zero crossing of the
    summed signal within +-zc_ms.
    """
    x = np.sum([np.asarray(s, dtype=np.float64) for s in signals], axis=0) if len(signals) > 1 \
        else np.asarray(signals[0], dtype=np.float64)
    energy = np.sum([np.asarray(s, dtype=np.float64) ** 2 for s in signals], axis=0)
    r = int(radius_ms * sr / 1000)
    w = max(1, int(frame_ms * sr / 1000))
    lo, hi = max(center - r, 0), min(center + r + 1, len(x))
    if hi <= lo:
        return center
    cs = np.concatenate([[0.0], np.cumsum(energy)])
    idx = np.arange(lo, hi)
    a = np.clip(idx - w // 2, 0, len(x))
    b = np.clip(idx + w - w // 2, 0, len(x))
    e = (cs[b] - cs[a]) / np.maximum(b - a, 1)
    cost = 10 * np.log10(e + 1e-12) + distance_penalty_db * np.abs(idx - center) / max(r, 1)
    best = int(idx[np.argmin(cost)])
    z = int(zc_ms * sr / 1000)
    zlo, zhi = max(best - z, lo, 1), min(best + z + 1, hi)
    seg = x[zlo - 1:zhi]
    zc = np.nonzero(np.signbit(seg[1:]) != np.signbit(seg[:-1]))[0] + zlo
    if len(zc):
        best = int(zc[np.argmin(np.abs(zc - best))])
    return best


def snap_cut_media(pool: SourcePool, media_ids: Sequence[str], sample: int, sr: int, **kw) -> int:
    """`snap_cut` on source media around `sample` (reads only +-radius)."""
    r = int(kw.get("radius_ms", 150.0) * sr / 1000) + int(kw.get("frame_ms", 10.0) * sr / 1000)
    a = sample - r
    sigs = [pool.read(m, a, sample + r + 1) for m in media_ids]
    return a + snap_cut(sigs, r, sr, **kw)
