"""Clipping detection and repair (lacuna_core/declip.py) and how the render path applies it."""
import hashlib

import numpy as np
import pytest
import soundfile as sf

from lacuna_core import MediaRef, Renderer, RenderSettings, SourcePool, add_source_clip, new_timeline
from lacuna_core import declip
from lacuna_core.declip import Repair, find_runs, scan
from lacuna_core.export import timeline_source

SR = 48000


def speech_like(sec: float, seed: int = 1) -> np.ndarray:
    """Harmonic 'voice' with a wandering pitch and a syllable envelope, peak 1.0."""
    rng = np.random.default_rng(seed)
    out = []
    for f0 in rng.uniform(90, 220, max(1, int(sec / 2))):
        t = np.arange(2 * SR) / SR
        ph = 2 * np.pi * np.cumsum(f0 * (1 + 0.05 * np.sin(2 * np.pi * 3 * t))) / SR
        x = sum(k ** -1.2 * np.sin(k * ph + rng.uniform(0, 6.3)) for k in range(1, 25))
        out.append(x * (0.2 + 0.8 * np.abs(np.sin(2 * np.pi * 0.37 * t)) ** 3) + 0.002 * rng.standard_normal(len(t)))
    x = np.concatenate(out)
    return x / np.abs(x).max()


def reader(x):
    x32 = np.asarray(x, dtype=np.float32)
    return lambda a, b: x32[a:b].copy()


def old_detector_spots(x, sr=SR):
    """The detector before 2026-10-18: >= 3 samples in a row at |x| >= 0.989, merged within 0.25 s."""
    hot = np.abs(x) >= 0.989
    d = np.diff(np.concatenate([[0], hot.astype(np.int8), [0]]))
    out = []
    for s, e in zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)):
        if e - s >= 3 and (not out or s / sr - out[-1] > 0.25):
            out.append(s / sr)
    return len(out)


def restored(r: Repair, x) -> np.ndarray:
    return r.apply(np.asarray(x, dtype=np.float32), 0)


# ------------------------------------------------------------------ detection

@pytest.mark.parametrize("freq", [50.0, 100.0, 220.0, 1000.0])
def test_a_clean_loud_sine_has_no_clipping(freq):
    x = 0.999 * np.sin(2 * np.pi * freq * np.arange(4 * SR) / SR)
    assert old_detector_spots(x) > 0          # what made Pei's track show hundreds of spots
    r = scan(reader(x), len(x), SR)
    assert len(r.starts) == 0 and r.spots() == []


def test_loud_unclipped_speech_has_no_clipping():
    x = 0.999 * speech_like(20)
    assert len(scan(reader(x), len(x), SR).starts) == 0
    # in 16-bit too (quantisation makes neighbouring samples equal more often)
    q = np.round(x * 32767) / 32767
    assert len(scan(reader(q), len(q), SR).starts) == 0


def test_a_hard_clipped_sine_is_detected_once_per_half_period():
    f, n = 200.0, SR
    x = np.clip(1.3 * np.sin(2 * np.pi * f * np.arange(n) / SR), -0.9, 0.9)
    s, e = find_runs(x, 0.95 * 0.9)
    assert len(s) == pytest.approx(2 * f * n / SR, abs=1)
    assert np.all(np.abs(x[s]) == pytest.approx(0.9))
    # a run is the whole flat top: 1.3 sin = 0.9 for |phase - peak| <= acos(0.9/1.3)
    want = 2 * np.arccos(0.9 / 1.3) / (2 * np.pi * f) * SR
    assert np.median(e - s) == pytest.approx(want, abs=2)


def test_level_is_relative_to_the_sources_own_peak():
    # clipped at the converter, then turned down 6 dB in an editor: still clipping
    x = 0.5 * np.clip(1.2 * speech_like(10), -1, 1)
    r = scan(reader(x), len(x), SR)
    assert len(r.starts) > 0 and r.level == pytest.approx(0.95 * 0.5, rel=1e-3)
    # flat runs well below the peak (e.g. a held DC value) are not clipping
    y = 0.9 * speech_like(4)
    y[SR:SR + 50] = 0.3
    assert len(scan(reader(y), len(y), SR).starts) == 0


def test_mild_clipping_counts_far_fewer_spots_than_the_old_detector_on_normalised_speech():
    x = 0.999 * speech_like(60)
    lim = np.tanh(2.5 * x) / np.tanh(2.5) * 0.999       # a limiter pushing every loud syllable to the top
    assert old_detector_spots(lim) >= 8
    assert len(scan(reader(lim), len(lim), SR).spots()) <= 1


# ------------------------------------------------------------------ repair

def test_short_clips_are_restored_closer_to_the_original():
    ref = 1.25 * speech_like(30)                       # +2 dB over the converter's ceiling
    c = np.clip(ref, -1.0, 1.0)
    r = scan(reader(c), len(c), SR)
    assert r.fixed.mean() > 0.95                       # nearly all runs are short enough
    y = restored(r, c)
    assert y.dtype == np.float32 and np.all(np.isfinite(y))
    m = np.zeros(len(c), bool)
    for s, e, f in zip(r.starts, r.ends, r.fixed):
        if f:
            m[s:e] = True
    err_clipped = np.sum((c - ref)[m] ** 2)
    err_restored = np.sum((y - ref)[m] ** 2)
    assert err_restored < 0.25 * err_clipped
    # consistent: restored samples never fall below the clip level, and stay under the cap
    a = np.abs(y[m])
    assert a.min() >= r.level * (1 - 1e-6) and a.max() <= declip.CAP * r.level
    assert np.abs(y).max() > 1.0                       # the peaks come back above full scale (float)
    # untouched outside the repaired runs
    assert np.array_equal(y[~m], c[~m].astype(np.float32))


def test_long_runs_are_left_alone():
    t = np.arange(2 * SR) / SR
    c = np.clip(4.0 * np.sin(2 * np.pi * 80 * t), -1.0, 1.0)       # ~5 ms flat tops
    r = scan(reader(c), len(c), SR)
    assert len(r.starts) > 100 and not r.fixed.any()
    assert np.array_equal(restored(r, c), c.astype(np.float32))
    assert r.spots() and all(not ok for _, ok in r.spots())


def test_a_top_that_would_need_a_big_guess_is_left_alone():
    # short runs, but the waveform around them points far above the ceiling (a hard 40x overload)
    t = np.arange(SR) / SR
    c = np.clip(40 * 0.1 * np.sin(2 * np.pi * 1500 * t), -1.0, 1.0)   # 1500 Hz: runs of ~13 samples
    r = scan(reader(c), len(c), SR)
    assert len(r.starts) > 0 and not r.fixed.any()


def test_chunked_reads_and_blocks_give_the_same_samples(monkeypatch):
    ref = 1.25 * speech_like(12, seed=3)
    c = np.clip(ref, -1.0, 1.0).astype(np.float32)
    r = scan(reader(c), len(c), SR)
    whole = r.apply(c, 0)
    parts = np.concatenate([r.apply(c[a:a + 777], a) for a in range(0, len(c), 777)])
    assert np.array_equal(whole, parts)
    monkeypatch.setattr(declip, "_BLOCK", 30011)                     # many block edges
    r2 = scan(reader(c), len(c), SR)
    assert np.array_equal(r2.starts, r.starts) and np.array_equal(r2.fixed, r.fixed)
    assert np.allclose(r2.apply(c, 0), whole, atol=1e-4)


def test_repair_round_trips_through_bytes():
    c = np.clip(1.25 * speech_like(6), -1, 1)
    r = scan(reader(c), len(c), SR)
    r2 = Repair.from_bytes(r.to_bytes())
    assert np.array_equal(r2.apply(c.astype(np.float32), 0), r.apply(c.astype(np.float32), 0))
    assert r2.spots() == r.spots()


# ------------------------------------------------------------------ render path

@pytest.fixture
def clipped_wav(tmp_path):
    ref = 1.25 * speech_like(8)
    path = tmp_path / "Pei.wav"
    sf.write(str(path), np.clip(ref, -1, 1).astype(np.float32), SR, subtype="FLOAT")
    return MediaRef.probe(path), ref


def test_pool_and_export_source_play_the_repaired_samples(clipped_wav):
    m, ref = clipped_wav
    before = hashlib.sha256(open(m.path, "rb").read()).hexdigest()
    raw = sf.read(m.path, dtype="float32")[0]
    with SourcePool({m.media_id: m}) as p0:
        r = scan(lambda a, b: p0.read(m.media_id, a, b), m.frames, SR)
    tl = add_source_clip(new_timeline(SR, ["Pei"]), "Pei", m)
    with SourcePool({m.media_id: m}, repairs={m.media_id: r}) as pool:
        assert np.array_equal(pool.read(m.media_id, 0, m.frames), r.apply(raw, 0))
        y = np.concatenate(list(timeline_source(pool, tl, 1)()))[:, 0]
        # export keeps the restored peaks in float (> 0 dBFS) for the master's limiter
        assert np.abs(y).max() > 1.05
        mid = slice(SR // 10, -SR // 10)                 # away from the clip's fade in / out
        assert np.sum((y - ref)[mid] ** 2) < 0.5 * np.sum((raw - ref)[mid] ** 2)
        # preview: the soft clipper still keeps playback under full scale
        z = Renderer(pool, RenderSettings(channels=1)).render(tl, 0, tl.length)[:, 0]
        assert np.abs(z).max() < 1.0
        key_repaired = Renderer(pool, RenderSettings()).range_key(tl, 0, SR)
    with SourcePool({m.media_id: m}) as plain:
        assert Renderer(plain, RenderSettings()).range_key(tl, 0, SR) != key_repaired
    assert hashlib.sha256(open(m.path, "rb").read()).hexdigest() == before      # source untouched


def test_render_overhead_is_small(clipped_wav):
    import time
    m, _ = clipped_wav
    with SourcePool({m.media_id: m}) as p0:
        r = scan(lambda a, b: p0.read(m.media_id, a, b), m.frames, SR)
    tl = add_source_clip(new_timeline(SR, ["Pei"]), "Pei", m)

    def best(pool):
        rr = Renderer(pool, RenderSettings(channels=1))
        ts = []
        for _ in range(5):
            t0 = time.perf_counter()
            for a in range(0, tl.length, SR // 2):
                rr.render(tl, a, min(a + SR // 2, tl.length))
            ts.append(time.perf_counter() - t0)
        return min(ts)
    with SourcePool({m.media_id: m}) as plain, SourcePool({m.media_id: m}, repairs={m.media_id: r}) as fixed:
        base, rep = best(plain), best(fixed)
    assert rep < base * 1.5 + 0.01
