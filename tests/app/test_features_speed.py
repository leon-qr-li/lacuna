"""The faster feature code gives exactly what the original loops gave (the AI editor's input must not move)."""
import numpy as np

from lacuna_app import features


def fill_runs_reference(mask, val, maxlen):
    """features._fill_runs as it was first written: a frame-by-frame scan."""
    m = mask.copy()
    n = len(m)
    i = 0
    while i < n:
        if m[i] == val:
            j = i
            while j < n and m[j] == val:
                j += 1
            if j - i < maxlen and i > 0 and j < n:
                m[i:j] = not val
            i = j
        else:
            i += 1
    return m


def test_fill_runs_matches_the_scan():
    rng = np.random.default_rng(1)
    for _ in range(1500):
        m = rng.random(int(rng.integers(0, 80))) < rng.uniform(0.05, 0.95)
        for val in (True, False):
            for maxlen in (1, 3, 6, 30):
                got = features._fill_runs(m, val, maxlen)
                assert got.dtype == m.dtype
                assert np.array_equal(got, fill_runs_reference(m, val, maxlen)), (m, val, maxlen)


def test_pitch_is_the_same_in_any_block_size(monkeypatch):
    sr = features.SR
    t = np.arange(12 * sr) / sr
    rng = np.random.default_rng(2)
    f = 110 + 40 * np.sin(2 * np.pi * 0.3 * t)
    x = (0.3 * np.sin(2 * np.pi * np.cumsum(f) / sr) + 0.01 * rng.standard_normal(len(t))).astype(np.float32)
    act = np.ones(len(features.frame_db(x)), bool)
    act[300:340] = False
    spans = [(0.2, 4.0), (3.5, 7.25), (8.0, 11.9)]
    monkeypatch.setattr(features, "_PITCH_BLOCK", 10 ** 6)        # one block, one thread: the old code path
    whole = features.pitch_track(x, spans, act)
    monkeypatch.setattr(features, "_PITCH_BLOCK", 97)
    split = features.pitch_track(x, spans, act)
    assert np.array_equal(whole, split, equal_nan=True)
    voiced = whole[~np.isnan(whole)]
    assert len(voiced) > 500 and 60 < np.median(voiced) < 160
