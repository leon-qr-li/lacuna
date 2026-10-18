"""TruePeak.per_sample measures long buffers in overlapping blocks on threads; every row must equal
the one-call result (the limiter's gain and the reported true peak depend on it bit for bit)."""
import numpy as np

from lacuna_core import master


def test_blocks_match_one_call(monkeypatch):
    rng = np.random.default_rng(4)
    monkeypatch.setattr(master, "_TP_BLOCK", 1000)
    for n in (1, 40, 1999, 2000, 2001, 7777, 12345):
        for ch in (1, 2):
            x = rng.standard_normal((n, ch)) * rng.uniform(0.05, 1.5)
            assert np.array_equal(master.TruePeak(ch).per_sample(x), master._peaks(x)), (n, ch)


def test_streaming_peak_is_unchanged_by_chunking():
    rng = np.random.default_rng(6)
    x = rng.standard_normal((300_000, 2)) * 0.4
    whole = master.TruePeak(2)
    whole.add(x)
    split = master.TruePeak(2)
    for a in range(0, len(x), 44_100):
        split.add(x[a:a + 44_100])
    assert whole.finish() == split.finish()
