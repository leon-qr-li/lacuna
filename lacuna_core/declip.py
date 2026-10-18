"""Clipping (破音) detection and conservative repair, applied when a source is read.

A clipped run is a stretch of at least MIN_RUN consecutive samples pinned at the same value near the
source's own maximum: same sign, |x| >= LEVEL_FRAC * peak, and each sample within FLAT_TOL (relative)
of its neighbour. A loud but intact peak is curved, so it never stays flat for three samples (a 100 Hz
sine at full scale changes by ~9e-5 between the samples at its top; FLAT_TOL is 2e-5), while a
converter that ran out of range writes the same value again and again.

Repair (only short runs, <= MAX_RUN_S): the missing top is interpolated by least-squares
autoregressive interpolation (Janssen et al. 1986): an AR model of the surrounding ~12 ms predicts the
samples so the prediction error is smallest, re-estimated on the restored signal a few times. It is
*consistent*: a restored sample is never below the clip level (the active-set loop pins such samples to
the level and solves again). A run whose restored top would exceed CAP * level is not touched: that much
missing waveform is a guess, and a wrong guess sounds worse than the flat top. Runs longer than
MAX_RUN_S, and runs in a heavily overloaded passage (more than MAX_DENSITY of the context at the clip
level, where the model would only learn the flat tops), are left alone for the same reason.

Nothing writes the source. `scan` returns a `Repair` (sparse patches: positions + restored samples)
that `SourcePool` applies to what it reads; restored peaks may exceed 1.0, which the float render path
carries to the master's limiter (export) or the preview soft clipper.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from scipy.linalg import solve_toeplitz

VERSION = 1                 # bump when detection or repair changes (invalidates cached repairs)
MIN_RUN = 3                 # samples pinned in a row
LEVEL_FRAC = 0.95           # ... at >= this fraction of the source's own peak
FLAT_TOL = 2e-5             # ... each within this (relative) of its neighbour
MIN_PEAK = 1e-3             # a source quieter than this has nothing that can clip
MAX_RUN_S = 0.002           # longer runs are left alone (2 ms = 96 samples at 48 kHz)
CTX_S = 0.0125              # AR context on each side
AR_ORDER = 16
AR_ITERS = 3
CAP = 1.5                   # a restored top above CAP * level is too much of a guess
MAX_DENSITY = 0.2           # ... and so is a run whose surroundings are clipped this much (heavy overload)
MERGE_S = 0.25              # runs closer than this are one spot (what Leon would hear as one 破音)
_BLOCK = 1 << 20

Reader = Callable[[int, int], np.ndarray]


def find_runs(x: np.ndarray, level: float, tol: float = FLAT_TOL,
              min_run: int = MIN_RUN) -> tuple[np.ndarray, np.ndarray]:
    """[start, end) of every run of >= min_run samples pinned at one value with |x| >= level."""
    x = np.asarray(x, dtype=np.float64)
    if len(x) < min_run or level <= 0:
        return np.zeros(0, np.int64), np.zeros(0, np.int64)
    a = np.abs(x)
    hot = a >= level
    pair = hot[:-1] & hot[1:] & (np.signbit(x[:-1]) == np.signbit(x[1:])) \
        & (np.abs(np.diff(x)) <= tol * a[:-1] + 1e-12)
    d = np.diff(np.concatenate([[0], pair.astype(np.int8), [0]]))
    s, e = np.flatnonzero(d == 1), np.flatnonzero(d == -1) + 1     # pair run i..j -> samples i..j+1
    keep = (e - s) >= min_run
    return s[keep].astype(np.int64), e[keep].astype(np.int64)


def _ar(y: np.ndarray, p: int) -> np.ndarray:
    w = y * np.hanning(len(y))
    r = np.array([np.dot(w[:len(w) - k], w[k:]) for k in range(p + 1)])
    r[0] = r[0] * (1 + 1e-6) + 1e-12            # a touch of white noise keeps the system well posed
    return np.concatenate([[1.0], solve_toeplitz(r[:p], -r[1:p + 1])])


def _interp(y: np.ndarray, s: int, e: int, a: np.ndarray, level: float, sign: float) -> np.ndarray:
    """Samples y[s:e] that minimise the AR prediction error with |y| >= level (y has p samples of
    context on both sides of [s, e))."""
    p = len(a) - 1
    lo, hi = s - p, e + p
    n_rows, n_cols = e - s + p, hi - lo
    rows = np.arange(n_rows)[:, None]
    cols = rows + np.arange(p + 1)[None, :]        # row i covers columns i .. i+p (times s-p+i .. s+i)
    A = np.zeros((n_rows, n_cols))
    A[rows, cols] = a[::-1]
    unk = np.zeros(n_cols, bool)
    unk[p:p + e - s] = True
    yy = y[lo:hi].astype(np.float64).copy()
    for _ in range(8):
        sol = np.linalg.lstsq(A[:, unk], -A[:, ~unk] @ yy[~unk], rcond=None)[0]
        yy[unk] = sol
        low = unk & (sign * yy < level)
        if not low.any():
            break
        yy[low] = sign * level
        unk &= ~low
    return yy[p:p + e - s]


def repair_run(y: np.ndarray, s: int, e: int, level: float, sr: int) -> np.ndarray | None:
    """Restored samples for the clipped run y[s:e], or None when it is better left alone."""
    ctx = int(CTX_S * sr)
    if e - s > int(MAX_RUN_S * sr) or s < ctx or e + ctx > len(y):
        return None
    sign = 1.0 if y[s] > 0 else -1.0
    w = np.array(y[s - ctx:e + ctx], dtype=np.float64)      # a local copy: the window being restored
    around = np.concatenate([w[:ctx], w[-ctx:]])
    if np.mean(np.abs(around) >= level) > MAX_DENSITY:      # the model would learn the flat tops
        return None
    try:
        for _ in range(AR_ITERS):
            out = _interp(w, ctx, ctx + e - s, _ar(w, AR_ORDER), level, sign)
            w[ctx:ctx + e - s] = out
    except (np.linalg.LinAlgError, ValueError):
        return None
    if not np.all(np.isfinite(out)) or np.max(sign * out) > CAP * level:
        return None
    return out.astype(np.float32)


@dataclass
class Repair:
    """Clipped runs of one source and the restored samples of those that were repaired."""
    sr: int
    level: float = 0.0
    starts: np.ndarray = field(default_factory=lambda: np.zeros(0, np.int64))
    ends: np.ndarray = field(default_factory=lambda: np.zeros(0, np.int64))
    fixed: np.ndarray = field(default_factory=lambda: np.zeros(0, bool))
    values: np.ndarray = field(default_factory=lambda: np.zeros(0, np.float32))  # fixed runs, in order

    def __post_init__(self):
        lens = np.where(self.fixed, self.ends - self.starts, 0)
        self._off = np.concatenate([[0], np.cumsum(lens)]).astype(np.int64)
        self._fs = self.starts[self.fixed]
        self._fe = self.ends[self.fixed]
        self._fo = self._off[:-1][self.fixed]

    def apply(self, x: np.ndarray, start: int) -> np.ndarray:
        """`x` = source samples [start, start + len(x)) with the repaired runs restored (a copy when
        anything changes)."""
        if not len(self._fs):
            return x
        stop = start + len(x)
        i = int(np.searchsorted(self._fe, start, side="right"))
        j = int(np.searchsorted(self._fs, stop, side="left"))
        if i >= j:
            return x
        x = x.copy()
        for s, e, o in zip(self._fs[i:j], self._fe[i:j], self._fo[i:j]):
            a, b = max(s, start), min(e, stop)
            x[a - start:b - start] = self.values[o + a - s:o + b - s]
        return x

    def spots(self, merge_s: float = MERGE_S) -> list[tuple[int, bool]]:
        """(first sample, all repaired) of each spot: runs starting within merge_s of a spot's first run
        belong to it."""
        out: list[tuple[int, bool]] = []
        gap = int(merge_s * self.sr)
        for s, f in zip(self.starts.tolist(), self.fixed.tolist()):
            if out and s - out[-1][0] <= gap:
                out[-1] = (out[-1][0], out[-1][1] and f)
            else:
                out.append((s, f))
        return out

    # ------------------------------------------------------------------ persistence
    def to_bytes(self) -> bytes:
        b = io.BytesIO()
        np.savez_compressed(b, version=VERSION, sr=self.sr, level=self.level, starts=self.starts,
                            ends=self.ends, fixed=self.fixed, values=self.values)
        return b.getvalue()

    @classmethod
    def from_bytes(cls, data: bytes) -> "Repair | None":
        with np.load(io.BytesIO(data)) as z:
            if int(z["version"]) != VERSION:
                return None
            return cls(int(z["sr"]), float(z["level"]), z["starts"].astype(np.int64), z["ends"].astype(np.int64),
                       z["fixed"].astype(bool), z["values"].astype(np.float32))


def scan(read: Reader, frames: int, sr: int) -> Repair:
    """Detect the clipped runs of a whole source (streamed, two passes) and repair the short ones."""
    peak = 0.0
    for s in range(0, frames, _BLOCK):
        peak = max(peak, float(np.abs(read(s, min(s + _BLOCK, frames))).max(initial=0.0)))
    if peak < MIN_PEAK:
        return Repair(sr)
    level = LEVEL_FRAC * peak
    ctx = int(CTX_S * sr)
    margin = ctx + int(MAX_RUN_S * sr) + AR_ORDER + MIN_RUN + 2
    starts: list[int] = []
    ends: list[int] = []
    fixed: list[bool] = []
    values: list[np.ndarray] = []
    for b0 in range(0, frames, _BLOCK):
        lo, hi = max(b0 - margin, 0), min(b0 + _BLOCK + margin, frames)
        y = read(lo, hi).astype(np.float64)
        # runs the previous block repaired that reach into this one count as restored context
        for s, e, v in zip(starts[::-1], ends[::-1], values[::-1]):
            if e <= lo:
                break
            if v is not None:
                a, b = max(s, lo), min(e, hi)
                y[a - lo:b - lo] = v[a - s:b - s]
        rs, re_ = find_runs(y, level)
        for s, e in zip(rs.tolist(), re_.tolist()):
            gs, ge = s + lo, e + lo
            if not (b0 <= gs < b0 + _BLOCK) or (s == 0 and lo > 0):
                continue              # another block owns it (or it began before this buffer)
            if e == len(y) and hi < frames:
                ge = hi               # runs on past the buffer: far longer than MAX_RUN_S
                v = None
            else:
                v = repair_run(y, s, e, level, sr)
            if v is not None:
                y[s:e] = v
            starts.append(gs)
            ends.append(ge)
            fixed.append(v is not None)
            values.append(v)
    kept = [v for v in values if v is not None]
    return Repair(sr, level, np.array(starts, np.int64), np.array(ends, np.int64), np.array(fixed, bool),
                  np.concatenate(kept).astype(np.float32) if kept else np.zeros(0, np.float32))
