"""Mastering: loudness metering (ITU-R BS.1770-4) and a gentle, streaming speech master chain.

Chain (per sample, all channels linked):

    high-pass (rumble) -> pre-gain -> compressor -> make-up gain -> true-peak limiter

The compressor is deliberately light (2:1, soft knee, slow release, threshold placed relative to
the programme's own loudness) so the conversation keeps its dynamics; the limiter is a safety
net that only touches the rare peaks left after make-up gain. Gains are found by measurement:

    pass 1  measure input loudness            -> pre-gain puts the programme at REF_LUFS
    pass 2  measure loudness after compression -> make-up gain hits the target
    pass 3  full chain -> file (+ one correction pass if the limiter moved loudness > 0.3 LU)

Everything streams in chunks with O(chunk) memory (an hour of 48 kHz stereo never sits in RAM),
and the source is a zero-argument callable returning an iterator of float chunks, called once per
pass, so the timeline is simply re-rendered (the renderer is ~200x real time).
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Iterator

import numpy as np
import soundfile as sf
from scipy.ndimage import minimum_filter1d, uniform_filter1d
from scipy.signal import butter, firwin, sosfilt, sosfilt_zi, upfirdn

Source = Callable[[], Iterable[np.ndarray]]
Progress = Callable[[float, str], None]

REF_LUFS = -23.0           # level the compressor sees (after pre-gain)
TP_OVERSAMPLE = 4
# 48-tap, 4-phase interpolator (the structure BS.1770-4 Annex 2 recommends). Like any 4x meter it
# can under-read by up to ~0.3 dB above 16 kHz, hence the limiter margin below.
_TP_FIR = firwin(48, 1 / TP_OVERSAMPLE, window=("kaiser", 5.0)) * TP_OVERSAMPLE
_TP_DELAY = (len(_TP_FIR) - 1) / 2          # in oversampled samples (23.5)
_SILENCE = -70.0


# ===================================================================== metering

def k_weighting(sr: int) -> np.ndarray:
    """BS.1770 K-weighting (pre-filter shelf + RLB high-pass) as SOS for any sample rate.

    Same construction as libebur128; reproduces the published 48 kHz coefficients."""
    f0, g, q = 1681.974450955533, 3.999843853973347, 0.7071752369554196
    k = math.tan(math.pi * f0 / sr)
    vh = 10 ** (g / 20)
    vb = vh ** 0.4996667741545416
    a0 = 1 + k / q + k * k
    shelf = [(vh + vb * k / q + k * k) / a0, 2 * (k * k - vh) / a0, (vh - vb * k / q + k * k) / a0,
             1.0, 2 * (k * k - 1) / a0, (1 - k / q + k * k) / a0]
    f0, q = 38.13547087602444, 0.5003270373238773
    k = math.tan(math.pi * f0 / sr)
    a0 = 1 + k / q + k * k
    hp = [1.0, -2.0, 1.0, 1.0, 2 * (k * k - 1) / a0, (1 - k / q + k * k) / a0]
    return np.array([shelf, hp])


def _2d(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    return x[:, None] if x.ndim == 1 else x


class TruePeak:
    """Streaming true-peak (4x oversampled) detector; chunking does not change the result."""

    CTX = 32   # input samples of context on each side (> half the polyphase filter length)

    def __init__(self, channels: int):
        self.buf = np.zeros((self.CTX, channels))   # left context (already measured)
        self.peak = 0.0

    def per_sample(self, x: np.ndarray) -> np.ndarray:
        """Max |oversampled signal| in [t, t+1) for every row of a buffer (edges unreliable)."""
        n, up = len(x), TP_OVERSAMPLE
        y = upfirdn(_TP_FIR, x, up=up, axis=0)
        o = int(_TP_DELAY + 0.5) - up // 2      # first of the `up` points within +-0.5 sample of t
        peak = np.abs(x)
        for p in range(up):
            np.maximum(peak, np.abs(y[o + p: o + p + up * n: up]), out=peak)
        return peak.max(axis=1)

    def _measure(self, b: np.ndarray, upto: int) -> None:
        if upto > self.CTX:
            self.peak = max(self.peak, float(self.per_sample(b)[self.CTX:upto].max()))

    def add(self, x: np.ndarray) -> None:
        b = np.concatenate([self.buf, _2d(x)])
        if len(b) >= 3 * self.CTX:
            self._measure(b, len(b) - self.CTX)
            self.buf = b[-2 * self.CTX:]
        else:
            self.buf = b

    def finish(self) -> float:
        b = np.concatenate([self.buf, np.zeros((self.CTX, self.buf.shape[1]))])
        self._measure(b, len(b) - self.CTX)
        self.buf = b[:0]
        return self.peak


def db(x: float) -> float:
    return 20 * math.log10(x) if x > 0 else -math.inf


class LoudnessMeter:
    """Integrated loudness (BS.1770-4 gating) + true peak, fed chunk by chunk.

    `dual_mono`: a mono programme is measured as if played on both speakers (+3.01 dB), which is
    how it is heard on a podcast app and what the -16 LUFS stereo convention means."""

    def __init__(self, sr: int, channels: int, dual_mono: bool = True, true_peak: bool = True):
        self.sr, self.channels = sr, channels
        self.sos = k_weighting(sr)
        self.zi = np.repeat(sosfilt_zi(self.sos)[:, :, None], channels, axis=2) * 0.0
        self.step = int(round(0.1 * sr))           # 100 ms sub-blocks, 400 ms blocks
        self.acc = np.zeros(0)
        self.sub: list[float] = []                 # channel-summed mean square per sub-block
        self.weight = 2.0 if (channels == 1 and dual_mono) else 1.0
        self.tp = TruePeak(channels) if true_peak else None
        self.samples = 0

    def add(self, x: np.ndarray) -> None:
        x = _2d(x)
        if not len(x):
            return
        self.samples += len(x)
        if self.tp:
            self.tp.add(x)
        y, self.zi = sosfilt(self.sos, x, axis=0, zi=self.zi)
        e = np.concatenate([self.acc, (y ** 2).sum(axis=1)])
        n = len(e) // self.step * self.step
        if n:
            self.sub.extend(e[:n].reshape(-1, self.step).mean(axis=1).tolist())
        self.acc = e[n:]

    def integrated(self) -> float:
        s = np.asarray(self.sub)
        if len(s) < 4:
            return -math.inf
        z = self.weight * np.convolve(s, np.ones(4) / 4, mode="valid")   # 400 ms, 75 % overlap
        lk = lambda v: -0.691 + 10 * np.log10(np.maximum(v, 1e-30))        # noqa: E731
        z = z[lk(z) > _SILENCE]
        if not len(z):
            return -math.inf
        z = z[lk(z) > lk(z.mean()) - 10.0]
        return float(lk(z.mean()))

    def true_peak_db(self) -> float:
        return db(self.tp.finish()) if self.tp else math.nan


def measure(chunks: Iterable[np.ndarray], sr: int, channels: int, dual_mono: bool = True) -> tuple[float, float]:
    """(integrated LUFS, true peak dBTP) of a stream of chunks."""
    m = LoudnessMeter(sr, channels, dual_mono)
    for c in chunks:
        m.add(c)
    return m.integrated(), m.true_peak_db()


# ===================================================================== processing

@dataclass(frozen=True)
class MasterSettings:
    target_lufs: float = -16.0      # Apple / Spotify podcast convention (stereo)
    true_peak_db: float = -1.0      # max true peak of the master (dBTP)
    highpass_hz: float = 60.0       # 0 disables; removes rumble/plosive thumps under voices
    comp_threshold_db: float = 0.0  # relative to REF_LUFS: loud syllables, laughs, shouts
    comp_ratio: float = 2.0
    comp_knee_db: float = 8.0
    comp_attack_ms: float = 20.0
    comp_release_ms: float = 300.0
    limiter_ms: float = 2.0         # limiter attack = release radius
    tolerance_lu: float = 0.3       # re-run the last pass once if output misses target by more
    dual_mono: bool = True


@dataclass
class MasterReport:
    sample_rate: int
    channels: int
    duration_s: float
    input_lufs: float
    input_true_peak_db: float
    output_lufs: float
    output_true_peak_db: float
    gain_db: float                  # pre-gain + make-up (static)
    comp_max_gr_db: float           # max compressor gain reduction
    comp_mean_gr_db: float          # mean reduction over blocks where it acted
    limiter_max_gr_db: float
    limiter_active_pct: float       # % of samples the limiter touched (> 0.1 dB)
    passes: int
    settings: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        def clean(v):
            if isinstance(v, float):
                return None if not math.isfinite(v) else round(v, 2)
            return v
        return {k: clean(v) for k, v in self.__dict__.items()}


class _HighPass:
    def __init__(self, hz: float, sr: int, channels: int):
        self.sos = butter(4, hz, "highpass", fs=sr, output="sos") if hz > 0 else None
        if self.sos is not None:
            self.zi = np.zeros((self.sos.shape[0], 2, channels))

    def __call__(self, x: np.ndarray) -> np.ndarray:
        if self.sos is None or not len(x):
            return x
        y, self.zi = sosfilt(self.sos, x, axis=0, zi=self.zi)
        return y


class _Compressor:
    """Feed-forward RMS compressor evaluated on 10 ms blocks (aligned to absolute time) with
    the gain ramped linearly across each block, so it is click-free, chunk-independent and fast
    in numpy (one Python step per block, not per sample)."""

    def __init__(self, s: MasterSettings, sr: int, channels: int):
        self.block = max(1, sr // 100)
        bs = self.block / sr
        self.att = 1 - math.exp(-bs / (s.comp_attack_ms / 1000))
        self.rel = 1 - math.exp(-bs / (s.comp_release_ms / 1000))
        self.thr = REF_LUFS + s.comp_threshold_db
        self.ratio, self.knee = s.comp_ratio, s.comp_knee_db
        self.env = None        # smoothed level, dB
        self.g = 1.0           # gain at the end of the previous block
        self.pending = np.zeros((0, channels))
        self.gr_max = 0.0
        self.gr_sum = 0.0
        self.gr_n = 0

    def _gr(self, level: float) -> float:
        """Gain reduction (dB, >= 0) for a detector level, soft knee."""
        over = level - self.thr
        k = self.knee / 2
        if over <= -k:
            return 0.0
        slope = 1 - 1 / self.ratio
        if over >= k:
            return slope * over
        return slope * (over + k) ** 2 / (2 * self.knee)

    def _run(self, x: np.ndarray) -> np.ndarray:
        n, B = len(x), self.block
        nb = -(-n // B)
        ms = np.zeros(nb)
        sq = (x ** 2).mean(axis=1)
        full = n // B * B
        if full:
            ms[: n // B] = sq[:full].reshape(-1, B).mean(axis=1)
        if full < n:
            ms[-1] = sq[full:].mean()
        lvl = 10 * np.log10(np.maximum(ms, 1e-12))
        gains = np.empty(nb)
        env = self.env
        for i in range(nb):
            v = lvl[i]
            if env is None:
                env = v
            else:
                env += (self.att if v > env else self.rel) * (v - env)
            gr = self._gr(env)
            if gr > 0.01:
                self.gr_sum += gr
                self.gr_n += 1
                if gr > self.gr_max:
                    self.gr_max = gr
            gains[i] = 10 ** (-gr / 20)
        self.env = env
        prev = np.concatenate([[self.g], gains[:-1]])
        frac = (np.arange(B) + 1) / B
        curve = (prev[:, None] + (gains - prev)[:, None] * frac[None, :]).reshape(-1)[:n]
        self.g = gains[-1]
        return x * curve[:, None]

    def __call__(self, x: np.ndarray, final: bool = False) -> np.ndarray:
        b = np.concatenate([self.pending, x])
        n = len(b) if final else len(b) // self.block * self.block
        self.pending = b[n:]
        return self._run(b[:n]) if n else b[:0]


class _Limiter:
    """Look-ahead true-peak limiter with a provable ceiling: per-sample required gain
    r(t) = min(1, ceiling / truepeak(t)); g = boxcar(minfilter(r, 2W+1), 2W+1). Each box term
    is a minimum over a window that contains t, so g(t) <= r(t) everywhere, and g is smooth
    (attack/release = W). Output is delayed internally and released in order."""

    def __init__(self, ceiling_db: float, ms: float, sr: int, channels: int):
        self.c = 10 ** (ceiling_db / 20)
        self.w = max(1, int(round(ms * sr / 1000)))
        self.ctx = 2 * self.w + TruePeak.CTX
        self.buf = np.zeros((self.ctx, channels))   # left context, already emitted
        self.tp = TruePeak(channels)                 # only its per-sample detector is used
        self.max_gr = 0.0
        self.active = 0

    def _emit(self, b: np.ndarray) -> np.ndarray:
        r = np.minimum(1.0, self.c / np.maximum(self.tp.per_sample(b), 1e-12))
        g = uniform_filter1d(minimum_filter1d(r, 2 * self.w + 1, mode="nearest"),
                             2 * self.w + 1, mode="nearest")
        g = np.minimum(g, r)    # guards boxcar float rounding
        g = g[self.ctx: len(b) - self.ctx]
        if len(g):
            gr = -20 * np.log10(g.min())
            self.max_gr = max(self.max_gr, float(gr))
            self.active += int((g < 0.9886).sum())    # > 0.1 dB
        return b[self.ctx: len(b) - self.ctx] * g[:, None]

    def __call__(self, x: np.ndarray, final: bool = False) -> np.ndarray:
        b = np.concatenate([self.buf, x])
        if final:
            b = np.concatenate([b, np.zeros((self.ctx, b.shape[1]))])
        if len(b) < 2 * self.ctx + 1:
            self.buf = b
            return b[:0]
        out = self._emit(b)
        self.buf = b[len(b) - 2 * self.ctx:]
        return out


class _Chain:
    def __init__(self, s: MasterSettings, sr: int, ch: int, pre_db: float,
                 makeup_db: float | None, limit: bool):
        self.hp = _HighPass(s.highpass_hz, sr, ch)
        self.pre = 10 ** (pre_db / 20)
        self.comp = _Compressor(s, sr, ch)
        self.makeup = 1.0 if makeup_db is None else 10 ** (makeup_db / 20)
        self.lim = _Limiter(s.true_peak_db - 0.3, s.limiter_ms, sr, ch) if limit else None

    def __call__(self, x: np.ndarray | None) -> np.ndarray:
        final = x is None
        if final:
            x = np.zeros((0, self.comp.pending.shape[1]))
        else:
            x = self.hp(_2d(x)) * self.pre
        y = self.comp(x, final) * self.makeup
        return self.lim(y, final) if self.lim else y


def _passes(source: Source, total: int, progress: Progress | None, label: str, i: int, n: int) -> Iterator[np.ndarray]:
    done = 0
    for c in source():
        done += len(c)
        yield c
        if progress and total:
            progress((i + min(done / total, 1.0)) / n, label)


def master(source: Source, sr: int, channels: int, out_path: str | Path,
           settings: MasterSettings = MasterSettings(), total: int = 0,
           progress: Progress | None = None, subtype: str = "PCM_24") -> MasterReport:
    """Master `source` to a WAV at `out_path` (temp file + atomic rename)."""
    s = settings
    n_pass = 4                     # progress slots: measure, analyse, master, correction
    if progress:                   # never let the bar move backwards on a second correction
        report, best = progress, [0.0]

        def progress(f: float, stage: str) -> None:
            best[0] = max(best[0], f)
            report(best[0], stage)
    meter = lambda tp=False: LoudnessMeter(sr, channels, s.dual_mono, tp)   # noqa: E731

    # pass 1: input loudness (after the high-pass, which is part of the programme)
    m, hp = meter(), _HighPass(s.highpass_hz, sr, channels)
    raw_tp = TruePeak(channels)
    for c in _passes(source, total, progress, "测量响度", 0, n_pass):
        c = _2d(c)
        raw_tp.add(c)
        m.add(hp(c))
    in_lufs, in_tp = m.integrated(), db(raw_tp.finish())
    pre = 0.0 if not math.isfinite(in_lufs) else REF_LUFS - in_lufs

    # pass 2: loudness after compression
    m, chain = meter(), _Chain(s, sr, channels, pre, None, limit=False)
    for c in _passes(source, total, progress, "分析动态", 1, n_pass):
        m.add(chain(c))
    m.add(chain(None))
    comp_lufs = m.integrated()
    makeup = 0.0 if not math.isfinite(comp_lufs) else s.target_lufs - comp_lufs

    # pass 3 (+ up to two corrections): full chain to file. Heavy limiting lowers loudness a
    # little more each time make-up rises, so corrections use the measured slope (secant).
    out_path = Path(out_path)
    tmp = out_path.with_name(out_path.name + ".part")
    passes, tried = 2, []
    for attempt in range(3):
        passes += 1
        chain = _Chain(s, sr, channels, pre, makeup, limit=True)
        m = meter(True)
        with sf.SoundFile(str(tmp), "w", sr, channels, subtype=subtype, format="WAV") as f:
            for c in _passes(source, total, progress, "母带处理", min(2 + attempt, n_pass - 1), n_pass):
                y = chain(c)
                m.add(y)
                f.write(y.astype(np.float32))
            y = chain(None)
            m.add(y)
            f.write(y.astype(np.float32))
        out_lufs = m.integrated()
        if not math.isfinite(out_lufs):
            break
        miss = s.target_lufs - out_lufs
        tried.append((makeup, out_lufs))
        if abs(miss) <= s.tolerance_lu or attempt == 2:
            break
        slope = 1.0
        if len(tried) > 1:
            (m0, l0), (m1, l1) = tried[-2:]
            if m1 != m0:
                slope = min(max((l1 - l0) / (m1 - m0), 0.25), 1.0)
        makeup += miss / slope
    os.replace(tmp, out_path)
    if progress:
        progress(1.0, "完成")
    comp = chain.comp
    return MasterReport(
        sample_rate=sr, channels=channels, duration_s=m.samples / sr,
        input_lufs=in_lufs, input_true_peak_db=in_tp,
        output_lufs=out_lufs, output_true_peak_db=m.true_peak_db(),
        gain_db=pre + makeup, comp_max_gr_db=float(comp.gr_max),
        comp_mean_gr_db=float(comp.gr_sum / comp.gr_n) if comp.gr_n else 0.0,
        limiter_max_gr_db=chain.lim.max_gr,
        limiter_active_pct=100.0 * chain.lim.active / max(m.samples, 1),
        passes=passes, settings=dict(s.__dict__))
