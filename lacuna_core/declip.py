"""Clipping repair: find flattened peaks in a source and reconstruct them, non-destructively.

A clipped recording has runs of samples pinned at the converter's ceiling. Each event (a cluster
of clipped runs) is rebuilt by least-squares autoregressive interpolation (Janssen et al. 1986):
an AR model is fitted to the clean audio around the event and the clipped samples are chosen to
minimise its prediction error, with the constraint that a rebuilt sample stays at least at the
ceiling on the side it was clipped (it can only have been louder). Reconstruction is only kept
when it is trustworthy; otherwise the event is left exactly as recorded:

* a run longer than MAX_RUN_S (the wave shape under it is guessed, not recovered);
* an event that is more than MAX_DENSITY clipped (sustained distortion, not a flattened peak);
* a rebuilt peak more than MAX_BOOST_DB over the ceiling, a rebuilt stretch the model predicts far
  worse than the clean audio around it (MAX_RESIDUAL), or a solve that does not converge.

The result is a `Patches` set: rebuilt samples by source position. The source file is never
written; `SourcePool` overlays the patches on read, so playback, export and every analysis that
reads through the pool hear the repaired audio while the original stays untouched.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import numpy as np
from scipy.linalg import solveh_banded

TOL = 0.011            # samples within 1.1 % (0.1 dB) of a polarity's maximum sit at the ceiling
MIN_RUN = 3            # this many in a row = a flattened peak (two equal samples happen naturally)
PILEUP = 4.0           # the ceiling band must be this many times denser than the band below it
PIN_TOL = 2e-5         # consecutive samples this close (relative, under 1 LSB at 16 bit) are pinned
MIN_CEILING = 0.25     # a "ceiling" lower than -12 dBFS is a quiet file, not clipping
MAX_RUN_S = 0.002      # longer runs are not rebuilt
MAX_DENSITY = 0.40     # more of the event window clipped than this: not rebuilt
MAX_RESIDUAL = 100.0   # rebuilt stretch this much less predictable than its context: not trusted
MAX_BOOST_DB = 9.0     # rebuilt peak more than this over the ceiling: not trusted
CONTEXT_S = 0.010      # clean audio each side used to fit the AR model
ORDER = 32             # AR order at 44.1/48 kHz (speech formants + harmonics)
ATTACK_S = 0.005       # a rebuilt peak over the ceiling is brought back by a gain dip this fast ...
RELEASE_S = 0.050      # ... that recovers over this long (a limiter's shape, local to the event)
MAX_SPAN_S = 0.040     # runs solved together span at most this (bounds the solve size)
MERGE_S = 0.25         # runs closer than this are one event in counts (as the old detector did)

SKIP_LONG, SKIP_DENSE, SKIP_UNSTABLE = "long", "dense", "unstable"


def _dip(t: np.ndarray, s: int, e: int, g: float, att: int, rel: int) -> np.ndarray:
    """Gain of one dip at samples `t`: 1 outside [s - att, e + rel), `g` on [s, e), raised-cosine
    ramps between."""
    w = np.zeros(len(t))
    w[(t >= s) & (t < e)] = 1.0
    up = (t >= s - att) & (t < s)
    w[up] = 0.5 - 0.5 * np.cos(np.pi * (t[up] - (s - att) + 0.5) / att)
    dn = (t >= e) & (t < e + rel)
    w[dn] = 0.5 + 0.5 * np.cos(np.pi * (t[dn] - e + 0.5) / rel)
    return 1.0 - (1.0 - g) * w


@dataclass
class Patches:
    """The repair of one source. Rebuilt samples: ``values[offsets[i]:offsets[i + 1]]`` replace
    source samples ``[starts[i], starts[i] + offsets[i + 1] - offsets[i])`` (starts sorted). Dips:
    where a rebuilt peak rose over its ceiling, a smooth gain dip (`_dip`: gain ``dip_g[i]`` on
    ``[dip_s[i], dip_e[i])``, ``att``/``rel`` samples of ramp) brings it back down; overlapping
    dips take the deeper gain. Stored as parameters, so the repair of an hour stays small."""
    starts: np.ndarray = field(default_factory=lambda: np.zeros(0, np.int64))
    offsets: np.ndarray = field(default_factory=lambda: np.zeros(1, np.int64))
    values: np.ndarray = field(default_factory=lambda: np.zeros(0, np.float32))
    dip_s: np.ndarray = field(default_factory=lambda: np.zeros(0, np.int64))
    dip_e: np.ndarray = field(default_factory=lambda: np.zeros(0, np.int64))
    dip_g: np.ndarray = field(default_factory=lambda: np.zeros(0, np.float64))
    att: int = 1
    rel: int = 1
    _digest: str | None = field(default=None, init=False, repr=False, compare=False)

    def __len__(self) -> int:
        return len(self.starts)

    @property
    def ends(self) -> np.ndarray:
        return self.starts + np.diff(self.offsets)

    def apply(self, start: int, buf: np.ndarray) -> np.ndarray:
        """Repair `buf` in place: it holds source samples [start, start + len(buf))."""
        if not len(self.starts) or not len(buf):
            return buf
        stop = start + len(buf)
        ends = self.ends
        lo = int(np.searchsorted(ends, start, side="right"))
        hi = int(np.searchsorted(self.starts, stop, side="left"))
        for i in range(lo, hi):
            s, e = int(self.starts[i]), int(ends[i])
            a, b = max(s, start), min(e, stop)
            if b > a:
                o = int(self.offsets[i])
                buf[a - start:b - start] = self.values[o + a - s:o + b - s]
        lo = int(np.searchsorted(self.dip_e, start - self.rel, side="right"))
        hi = int(np.searchsorted(self.dip_s, stop + self.att, side="left"))
        if hi > lo:
            a = max(int(self.dip_s[lo]) - self.att, start)
            b = min(int(self.dip_e[lo:hi].max()) + self.rel, stop)
            if b > a:
                env = np.ones(b - a)
                for i in range(lo, hi):
                    s, e = int(self.dip_s[i]), int(self.dip_e[i])
                    u, v = max(s - self.att, a), min(e + self.rel, b)
                    if v > u:
                        env[u - a:v - a] = np.minimum(env[u - a:v - a], _dip(np.arange(u, v), s, e, float(self.dip_g[i]),
                                                                            self.att, self.rel))
                buf[a - start:b - start] *= env.astype(buf.dtype)
        return buf

    def digest(self) -> str:
        if self._digest is None:
            h = hashlib.sha1(f"{self.att},{self.rel}".encode())
            for a in (self.starts, self.offsets, self.values, self.dip_s, self.dip_e, self.dip_g):
                h.update(np.ascontiguousarray(a).tobytes())
            self._digest = h.hexdigest()[:16]
        return self._digest

    def to_npz(self) -> dict:
        return {"starts": self.starts, "offsets": self.offsets, "values": self.values, "dip_s": self.dip_s,
                "dip_e": self.dip_e, "dip_g": self.dip_g, "ramps": np.array([self.att, self.rel], np.int64)}

    @classmethod
    def from_npz(cls, d) -> "Patches":
        att, rel = (int(v) for v in d["ramps"])
        return cls(np.asarray(d["starts"], np.int64), np.asarray(d["offsets"], np.int64),
                   np.asarray(d["values"], np.float32), np.asarray(d["dip_s"], np.int64),
                   np.asarray(d["dip_e"], np.int64), np.asarray(d["dip_g"], np.float64), att, rel)


@dataclass
class Report:
    """What a scan found and did, in source samples."""
    ceiling: tuple[float, float] = (0.0, 0.0)     # (+, -) clip levels, 0 = that side does not clip
    events: int = 0                                # clusters of runs (MERGE_S apart)
    repaired: int = 0                              # events rebuilt
    skipped: dict[str, int] = field(default_factory=dict)
    skipped_at: list[int] = field(default_factory=list)   # first sample of each skipped event
    event_at: list[int] = field(default_factory=list)     # first sample of each event (MERGE_S clusters)
    clipped_samples: int = 0
    longest_run: int = 0

    def to_dict(self, sr: int) -> dict:
        return {"ceiling": [round(c, 5) for c in self.ceiling], "events": self.events, "repaired": self.repaired,
                "skipped": dict(self.skipped), "skipped_at": [round(s / sr, 2) for s in self.skipped_at],
                "event_at": [round(s / sr, 2) for s in self.event_at],
                "clipped_ms": round(1000 * self.clipped_samples / sr, 1),
                "longest_run_ms": round(1000 * self.longest_run / sr, 2)}


# ===================================================================== detection

def piled_up(top: int, below: int) -> bool:
    """Samples crowd the TOL band under the maximum (4x wider band below it as reference): a
    ceiling the wave kept running into, even when its plateaus are not perfectly flat."""
    return top > 0 and top * 4 >= PILEUP * max(below, 1)


def runs_at(x: np.ndarray, level_pos: float, level_neg: float) -> list[tuple[int, int, int, bool]]:
    """(start, end, sign, pinned) of runs of at least MIN_RUN samples within TOL of a ceiling, in
    `x` indices. `pinned`: MIN_RUN samples in a row hold (nearly) the same value, as a converter
    out of range writes; a natural peak is curved and never does that at speech pitches."""
    out = []
    for sign, lev in ((1, level_pos), (-1, level_neg)):
        if lev <= 0:
            continue
        y = x * sign
        hot = y >= lev * (1 - TOL)
        if not hot.any():
            continue
        d = np.diff(np.concatenate([[0], hot.astype(np.int8), [0]]))
        s, e = np.flatnonzero(d == 1), np.flatnonzero(d == -1)
        keep = (e - s) >= MIN_RUN
        s, e = s[keep], e[keep]
        if not len(s):
            continue
        flat = np.abs(np.diff(y)) <= PIN_TOL * lev
        flat2 = np.concatenate([flat[:-1] & flat[1:], [False, False]])  # y[i], y[i+1], y[i+2] equal
        c = np.concatenate([[0], np.cumsum(flat2)])
        pinned = c[np.maximum(e - 2, s)] - c[s] > 0
        out += [(int(a), int(b), sign, bool(k)) for a, b, k in zip(s, e, pinned)]
    out.sort()
    return out


# ===================================================================== reconstruction

def _ar(seg: np.ndarray, clean: np.ndarray, p: int) -> np.ndarray | None:
    """AR coefficients [1, a1..ap] by least squares over every clean stretch of `seg`
    (covariance method: only predictions whose whole support is clean)."""
    n = len(seg)
    if n <= p + 1:
        return None
    bad = np.concatenate([[0], np.cumsum(~clean)])
    t = np.arange(p, n)
    ok = (bad[t + 1] - bad[t - p]) == 0                  # x[t-p..t] all clean
    t = t[ok]
    if len(t) < 3 * p:
        return None
    X = seg[t[:, None] - np.arange(1, p + 1)[None, :]]
    y = seg[t]
    scale = float(np.sqrt(np.mean(y ** 2))) or 1.0
    X = X / scale
    y = y / scale
    G = X.T @ X
    G[np.diag_indices(p)] += 1e-6 * len(t)             # light ridge keeps it well posed
    try:
        a = np.linalg.solve(G, -(X.T @ y))
    except np.linalg.LinAlgError:
        return None
    return np.concatenate([[1.0], a])


def _lsar(seg: np.ndarray, unknown: np.ndarray, a: np.ndarray) -> np.ndarray:
    """Values for seg[unknown] minimising the AR prediction error over the whole segment."""
    p = len(a) - 1
    x0 = seg.astype(np.float64).copy()
    x0[unknown] = 0.0
    e0 = np.convolve(x0, a)[p:len(seg)]            # residual rows t = p..n-1 (full support)
    idx = np.flatnonzero(unknown)
    # A_u^T A_u: entry (i, j) is the autocorrelation of a at lag |idx_i - idx_j| (unknowns are >= p
    # from both ends), zero beyond lag p. It is banded (at most p diagonals each side), and a banded
    # Cholesky solve also stays clear of OpenBLAS's threaded dense solver, which stalls for minutes
    # when several of these run at once.
    ra = np.correlate(a, a, "full")[p:]
    ra[0] *= 1.0 + 1e-9
    n = len(idx)
    u = min(p, n - 1)
    ab = np.zeros((u + 1, n))
    for k in range(u + 1):
        lag = idx[k:] - idx[:n - k]
        ab[u - k, k:] = np.where(lag <= p, ra[np.minimum(lag, p)], 0.0)
    # A_u^T e0: for unknown j, sum_k a_k e0[j + k - p]
    g = np.correlate(np.concatenate([np.zeros(p), e0, np.zeros(p)]), a, "valid")  # len = len(e0) + p
    return solveh_banded(ab, -g[idx])


def rebuild(seg: np.ndarray, clipped: np.ndarray, signs: np.ndarray, levels: np.ndarray,
            order: int = ORDER) -> np.ndarray | None:
    """Rebuild `seg[clipped]`; `signs`/`levels` per segment sample (used where clipped).
    Returns the new segment, or None when the reconstruction is not trustworthy."""
    first, last = np.flatnonzero(clipped)[[0, -1]]
    if first < order or len(seg) - 1 - last < order:
        return None
    a = _ar(seg, ~clipped, order)
    if a is None:
        return None
    unknown = clipped.copy()
    out = seg.astype(np.float64).copy()
    for _ in range(4):                            # consistency: rebuilt |x| >= ceiling, same sign
        try:
            vals = _lsar(out, unknown, a)
        except (np.linalg.LinAlgError, ValueError):
            return None
        out[unknown] = vals
        bad = clipped & unknown & (out * signs < levels)
        if not bad.any():
            break
        out[bad] = signs[bad] * levels[bad]       # pin to the ceiling and solve the rest again
        unknown &= ~bad
        if not unknown.any():
            break
    else:
        return None
    if not np.all(np.isfinite(out)):
        return None
    # the AR model must explain the rebuilt stretch about as well as the clean audio around it;
    # a rebuilt stretch it cannot predict is invented, not recovered
    p = len(a) - 1
    e = np.convolve(out, a)[p:len(out)] ** 2
    near = np.convolve(clipped, np.ones(p + 1))[p:len(out)] > 0
    if (~near).any() and e[near].mean() > MAX_RESIDUAL * max(e[~near].mean(), 1e-20):
        return None
    peak = np.max(np.abs(out[clipped]) / np.maximum(levels[clipped], 1e-9))
    if peak > 10 ** (MAX_BOOST_DB / 20):
        return None
    return out


# ===================================================================== whole-file scan

def scan(read, frames: int, sr: int, block_s: float = 30.0) -> tuple[Patches, Report]:
    """Find and repair clipping in one mono source. `read(a, b)` returns float samples [a, b)."""
    block = max(int(block_s * sr), 1)
    # pass 1: polarity maxima and the pile-up histogram just under them
    pmax = nmax = 0.0
    for s in range(0, frames, block):
        x = read(s, min(s + block, frames))
        if len(x):
            pmax, nmax = max(pmax, float(x.max())), max(nmax, float(-x.min()))
    hist: dict[str, tuple[int, int]] = {}
    for s in range(0, frames, block):
        x = read(s, min(s + block, frames))
        for side, m, v in (("+", pmax, x), ("-", nmax, -x)):
            if m <= 0:
                continue
            t, b = hist.get(side, (0, 0))
            t += int(np.count_nonzero(v >= m * (1 - TOL)))
            b += int(np.count_nonzero((v >= m * (1 - 5 * TOL)) & (v < m * (1 - TOL))))
            hist[side] = (t, b)
    piles = {sg for sg, side in ((1, "+"), (-1, "-")) if piled_up(*hist.get(side, (0, 0)))}
    lp, ln = (pmax if pmax >= MIN_CEILING else 0.0), (nmax if nmax >= MIN_CEILING else 0.0)
    rep = Report()
    if lp <= 0 and ln <= 0:
        return Patches(), rep
    # pass 2: runs (with a margin so runs crossing block edges are seen whole)
    runs: list[tuple[int, int, int]] = []
    margin = int(MAX_RUN_S * sr) * 4 + MIN_RUN
    for s in range(0, frames, block):
        a, b = max(s - margin, 0), min(s + block + margin, frames)
        for r0, r1, sg, pinned in runs_at(read(a, b), lp, ln):
            r0, r1 = r0 + a, r1 + a
            if s <= r0 < s + block:
                runs.append((r0, r1, sg, pinned))
    # a side clips when its peaks were pinned somewhere or crowd its ceiling; a clean (or
    # limited) recording whose loudest peaks merely come near their maximum is left alone
    clips = piles | {sg for *_, sg, pinned in runs if pinned}
    runs = sorted((r0, r1, sg) for r0, r1, sg, _ in runs if sg in clips)
    rep.ceiling = (lp if 1 in clips else 0.0, ln if -1 in clips else 0.0)
    if not runs:
        return Patches(), rep
    rep.clipped_samples = sum(e - s for s, e, _ in runs)
    rep.longest_run = max(e - s for s, e, _ in runs)
    merge = int(MERGE_S * sr)
    for s, _, _ in runs:
        if not rep.event_at or s - last > merge:
            rep.event_at.append(s)
        last = s
    rep.events = len(rep.event_at)
    # repair clusters: runs whose context windows touch are solved together (at most MAX_SPAN_S
    # of them at once; runs of a neighbouring cluster inside the window are solved too, not kept)
    ctx, span, max_run = int(CONTEXT_S * sr), int(MAX_SPAN_S * sr), int(MAX_RUN_S * sr)
    clusters: list[list[int]] = [[0]]
    for i in range(1, len(runs)):
        cl = clusters[-1]
        if runs[i][0] - runs[cl[-1]][1] < ctx and runs[i][1] - runs[cl[0]][0] <= span:
            cl.append(i)
        else:
            clusters.append([i])
    status = [""] * len(runs)                    # "" = repaired, else the skip reason
    rebuilt: list[tuple[int, int, np.ndarray, float]] = []
    r0s = np.asarray([r[0] for r in runs])
    for cl in clusters:
        mine = [i for i in cl if runs[i][1] - runs[i][0] <= max_run]
        for i in cl:
            if i not in mine:
                status[i] = SKIP_LONG
        if not mine:
            continue
        c0, c1 = runs[cl[0]][0], runs[cl[-1]][1]
        if sum(runs[i][1] - runs[i][0] for i in cl) > MAX_DENSITY * (c1 - c0) and c1 - c0 > max_run:
            for i in mine:
                status[i] = SKIP_DENSE
            continue
        w0, w1 = max(c0 - ctx, 0), min(c1 + ctx, frames)
        for _ in range(8):                       # no run within ORDER of a window edge
            near = range(max(int(np.searchsorted(r0s, w0 - max_run * 4)) - 1, 0),
                         int(np.searchsorted(r0s, w1 + ORDER, side="right")))
            n0, n1 = w0, w1
            for j in near:
                s, e, _ = runs[j]
                if e > w0 - 1 and s < w0 + ORDER + 1:
                    n0 = min(n0, max(s - ORDER - 2, 0))
                if s < w1 + 1 and e > w1 - ORDER - 1:
                    n1 = max(n1, min(e + ORDER + 2, frames))
            if (n0, n1) == (w0, w1):
                break
            w0, w1 = n0, n1
        seg = np.asarray(read(w0, w1), np.float64)
        clipped = np.zeros(len(seg), bool)
        signs = np.zeros(len(seg))
        levels = np.zeros(len(seg))
        for j in near:
            s, e, sg = runs[j]
            a, b = max(s, w0) - w0, min(e, w1) - w0
            if b > a:
                clipped[a:b] = True
                signs[a:b] = sg
                levels[a:b] = np.abs(seg[a:b])      # clipping only ever took amplitude away
        out = rebuild(seg, clipped, signs, levels)
        if out is None:
            for i in mine:
                status[i] = SKIP_UNSTABLE
            continue
        for i in mine:
            s, e, _ = runs[i]
            rebuilt.append((s, e, out[s - w0:e - w0], float(levels[s - w0:e - w0].max())))
    # an event (runs MERGE_S apart) counts as repaired only when every run in it was
    ev = np.asarray(rep.event_at)
    bad: dict[int, str] = {}
    for i, why in enumerate(status):
        if why:
            bad.setdefault(int(np.searchsorted(ev, runs[i][0], side="right")) - 1, why)
    for why in bad.values():
        rep.skipped[why] = rep.skipped.get(why, 0) + 1
    rep.repaired = rep.events - len(bad)
    rep.skipped_at = [int(ev[k]) for k in sorted(bad)]
    return peak_safe(sr, rebuilt), rep


def peak_safe(sr: int, rebuilt: list[tuple[int, int, np.ndarray, float]]) -> Patches:
    """Patches that are never louder than the recording: where a rebuilt peak rises over its
    ceiling, a smooth local gain dip (ATTACK_S in, RELEASE_S out, like a limiter but only around
    that peak) brings it back to the ceiling."""
    if not rebuilt:
        return Patches()
    rebuilt = sorted(rebuilt, key=lambda r: r[0])
    dips = []
    for s, e, v, lev in rebuilt:
        g = min(1.0, lev / max(float(np.max(np.abs(v))), 1e-12))
        if g < 1.0:
            dips.append((s, e, g))
    lens = np.array([len(v) for _, _, v, _ in rebuilt], np.int64)
    d = np.array(dips, dtype=np.float64).reshape(-1, 3)
    return Patches(np.array([r[0] for r in rebuilt], np.int64),
                   np.concatenate([[0], np.cumsum(lens)]).astype(np.int64),
                   np.concatenate([v for _, _, v, _ in rebuilt]).astype(np.float32),
                   d[:, 0].astype(np.int64), d[:, 1].astype(np.int64), d[:, 2].copy(),
                   max(int(ATTACK_S * sr), 1), max(int(RELEASE_S * sr), 1))
