import numpy as np
import pytest
import soundfile as sf

from lacuna_core import MediaRef, SourcePool

SR = 8000


def write(path, x, sr=SR):
    sf.write(str(path), np.asarray(x, dtype=np.float32), sr, subtype="FLOAT")
    return MediaRef.probe(path)


@pytest.fixture
def ramp_media(tmp_path):
    """Source whose sample value encodes its own index: x[n] = n / 1e6 (exact in float32 up
    to 2**24), so rendered output reveals exactly which source sample landed where."""
    def make(name, n, offset=0):
        return write(tmp_path / f"{name}.wav", (np.arange(n) + offset) / 1e6)
    return make


@pytest.fixture
def tone_media(tmp_path):
    def make(name, n, freq=220.0, amp=0.3, sr=SR):
        t = np.arange(n) / sr
        return write(tmp_path / f"{name}.wav", amp * np.sin(2 * np.pi * freq * t), sr)
    return make


@pytest.fixture
def noise_media(tmp_path):
    def make(name, n, amp=0.01, seed=0):
        return write(tmp_path / f"{name}.wav", amp * np.random.default_rng(seed).standard_normal(n))
    return make


@pytest.fixture
def pool_of():
    pools = []

    def make(*refs):
        p = SourcePool({r.media_id: r for r in refs})
        pools.append(p)
        return p
    yield make
    for p in pools:
        p.close()
