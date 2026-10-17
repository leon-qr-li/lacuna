import shutil

import numpy as np
import pytest
import soundfile as sf

from lacuna_core import MediaRef, content_hash
from lacuna_core.media import conform


def test_media_id_is_content_hash_not_path(tmp_path, ramp_media):
    m = ramp_media("A", 1000)
    copy = tmp_path / "renamed.wav"
    shutil.copy(m.path, copy)
    assert MediaRef.probe(copy).media_id == m.media_id == content_hash(m.path)
    assert MediaRef.from_dict(m.to_dict()) == m


def test_pool_reads_are_exact_and_zero_padded(ramp_media, pool_of):
    m = ramp_media("A", 1000)
    pool = pool_of(m)
    y = pool.read(m.media_id, -5, 5)
    assert np.all(y[:5] == 0) and np.array_equal(np.rint(y[5:] * 1e6), np.arange(5))
    assert np.all(pool.read(m.media_id, 995, 1010)[5:] == 0)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_conform_resamples_foreign_media(tmp_path):
    sr = 48000
    t = np.arange(sr) / sr
    x = 0.3 * np.stack([np.sin(2 * np.pi * 440 * t), np.sin(2 * np.pi * 440 * t)], axis=1)
    sf.write(str(tmp_path / "music.wav"), x, sr)
    m = conform(tmp_path / "music.wav", tmp_path / "proxy" / "music_8k.wav", 8000)
    assert (m.sample_rate, m.channels) == (8000, 1)
    assert abs(m.frames - 8000) <= 2
    assert (tmp_path / "music.wav").exists()          # source untouched


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_conform_without_soxr_falls_back_to_swr(tmp_path, monkeypatch):
    from lacuna_core import media
    monkeypatch.setattr(media, "ffmpeg_has_soxr", lambda: False)
    sr = 48000
    t = np.arange(sr) / sr
    sf.write(str(tmp_path / "music.wav"), 0.3 * np.sin(2 * np.pi * 440 * t), sr)
    m = conform(tmp_path / "music.wav", tmp_path / "music_8k.wav", 8000)
    assert (m.sample_rate, m.channels) == (8000, 1) and abs(m.frames - 8000) <= 2
    y, _ = sf.read(str(tmp_path / "music_8k.wav"))
    spec = np.abs(np.fft.rfft(y[1000:7000] * np.hanning(6000)))
    assert abs(np.argmax(spec) * 8000 / 6000 - 440) < 3      # tone preserved, not garbled
