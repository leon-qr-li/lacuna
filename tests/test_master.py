import math
import re
import shutil
import subprocess

import numpy as np
import pytest
import soundfile as sf

from lacuna_core import SetTrackGain, add_source_clip, new_timeline
from lacuna_core import export as export_mod
from lacuna_core.export import export, measure_file, timeline_source
from lacuna_core.master import (LoudnessMeter, MasterSettings, TruePeak, k_weighting, master,
                                measure)

FFMPEG = shutil.which("ffmpeg")
needs_ffmpeg = pytest.mark.skipif(not FFMPEG, reason="ffmpeg not installed")
SR = 48000


def chunks(x, n):
    return [x[i:i + n] for i in range(0, len(x), n)]


def speech_like(seconds, seed=1, level=0.15, shouts=6, sr=SR):
    """Noise shaped by a syllable envelope with pauses and a few loud bursts (laughs/shouts):
    the crest factor and dynamics of conversational speech, without needing real voices."""
    rng = np.random.default_rng(seed)
    n = int(seconds * sr)
    noise = np.convolve(rng.standard_normal(n), np.ones(6) / 6, "same")
    syl = np.repeat(rng.uniform(0.1, 1, n // (sr // 5) + 1), sr // 5)[:n]
    syl = np.convolve(syl, np.hanning(sr // 24) / (sr // 48), "same")
    gate = np.repeat(rng.uniform(0, 1, n // sr + 1) > 0.25, sr)[:n]
    x = level * noise * syl * gate
    for _ in range(shouts):
        a = rng.integers(0, max(n - sr, 1))
        x[a:a + sr // 2] *= 2.5
    return x


def src_of(x, n=SR * 5):
    x = x[:, None] if x.ndim == 1 else x
    return lambda: iter(chunks(x, n))


# ------------------------------------------------------------------ metering

def test_k_weighting_matches_bs1770_published_48k_coefficients():
    sos = k_weighting(48000)
    assert np.allclose(sos[0], [1.53512485958697, -2.69169618940638, 1.19839281085285,
                                1.0, -1.69065929318241, 0.73248077421585], atol=1e-9)
    assert np.allclose(sos[1], [1.0, -2.0, 1.0, 1.0, -1.99004745483398, 0.99007225036621], atol=1e-9)


@pytest.mark.parametrize("sr", [44100, 48000])
def test_1khz_sine_loudness(sr):
    t = np.arange(10 * sr) / sr
    x = 0.1 * np.sin(2 * np.pi * 1000 * t)          # -20 dBFS peak
    stereo, _ = measure(chunks(np.stack([x, x], 1), 7777), sr, 2)
    assert stereo == pytest.approx(-20.0, abs=0.05)
    assert measure([x], sr, 1)[0] == pytest.approx(stereo, abs=0.01)                 # dual mono
    assert measure([x], sr, 1, dual_mono=False)[0] == pytest.approx(stereo - 3.01, abs=0.02)


def test_gating_ignores_silence_and_quiet_passages():
    t = np.arange(10 * SR) / SR
    tone = 0.1 * np.sin(2 * np.pi * 1000 * t)
    ref = measure([tone], SR, 1)[0]
    with_silence = np.concatenate([tone, np.zeros(20 * SR)])
    assert measure([with_silence], SR, 1)[0] == pytest.approx(ref, abs=0.1)   # edge block only
    with_quiet = np.concatenate([tone, tone * 10 ** (-30 / 20)])   # 30 LU below: relative gate
    assert measure([with_quiet], SR, 1)[0] == pytest.approx(ref, abs=0.1)
    assert measure([np.zeros(5 * SR)], SR, 1)[0] == -math.inf


def test_true_peak_sees_intersample_peaks_and_is_chunk_independent():
    t = np.arange(SR) / SR
    x = 0.5 * np.sin(2 * np.pi * SR / 4 * t + np.pi / 4)    # samples land at +-0.354
    sample_peak = 20 * np.log10(np.abs(x).max())
    whole = measure([x], SR, 1)[1]
    assert whole > sample_peak + 2.5 and whole == pytest.approx(-6.02, abs=0.35)
    y = speech_like(3)
    a, b = TruePeak(1), TruePeak(1)
    a.add(y[:, None])
    for c in chunks(y[:, None], 1001):
        b.add(c)
    assert a.finish() == pytest.approx(b.finish(), rel=1e-12)


@needs_ffmpeg
def test_meter_agrees_with_ffmpeg_ebur128(tmp_path):
    x = speech_like(60, seed=3)
    p = tmp_path / "x.wav"
    sf.write(str(p), np.stack([x, 0.7 * x], 1).astype(np.float32), SR, subtype="FLOAT")
    lufs, tp = measure_file(p, SR, 2)
    out = subprocess.run([FFMPEG, "-hide_banner", "-nostats", "-i", str(p), "-af", "ebur128=peak=true",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    ff_i = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", out)[-1])
    ff_tp = float(re.findall(r"Peak:\s+(-?[\d.]+) dBFS", out)[-1])
    assert lufs == pytest.approx(ff_i, abs=0.15)
    assert tp == pytest.approx(ff_tp, abs=0.3)


# ------------------------------------------------------------------ master chain

def read(path):
    y, sr = sf.read(str(path), dtype="float64", always_2d=True)
    return y, sr


def test_master_hits_target_and_true_peak_on_overloaded_input(tmp_path):
    x = speech_like(120, level=0.3) * 10 ** (7 / 20)      # +7 dB like Leon: peaks far above 0 dBFS
    x = np.stack([x, x], 1)
    assert np.abs(x).max() > 1.5
    rep = master(src_of(x), SR, 2, tmp_path / "m.wav", total=len(x))
    y, sr = read(tmp_path / "m.wav")
    assert sr == SR and y.shape == x.shape                 # no samples gained or lost
    assert rep.input_true_peak_db > 3
    assert rep.output_lufs == pytest.approx(-16.0, abs=0.3)
    assert rep.output_true_peak_db <= -1.0
    lufs, tp = measure(chunks(y, 99999), SR, 2)           # re-measure the file independently
    assert lufs == pytest.approx(rep.output_lufs, abs=0.05)
    assert tp <= -1.0 + 0.05                              # 24-bit rounding
    assert np.abs(y).max() <= 10 ** (-1 / 20)
    assert not (tmp_path / "m.wav.part").exists()


def test_master_is_gentle_keeps_dynamics_and_timing(tmp_path):
    """Natural sound: a passage 6 dB quieter must stay clearly quieter (no flattening), the
    compressor must work only lightly on average, and nothing is shifted in time."""
    a = speech_like(40, seed=5, shouts=0)
    b = speech_like(40, seed=6, shouts=0) * 10 ** (-6 / 20)
    x = np.concatenate([a, b])
    rep = master(src_of(x), SR, 1, tmp_path / "m.wav", total=len(x))
    y = read(tmp_path / "m.wav")[0][:, 0]
    la = measure([y[:40 * SR]], SR, 1)[0]
    lb = measure([y[40 * SR:]], SR, 1)[0]
    assert 3.0 < la - lb < 6.2
    assert rep.comp_mean_gr_db < 2.5
    assert rep.limiter_active_pct < 1.0
    # timing: cross-correlation of input and output peaks at lag 0
    n = 2 ** 22
    corr = np.fft.irfft(np.fft.rfft(y[:n]) * np.conj(np.fft.rfft(x[:n])))
    assert int(np.argmax(np.r_[corr[-50:], corr[:51]])) == 50


def test_master_output_does_not_depend_on_chunking(tmp_path):
    x = speech_like(20, seed=9) * 3
    master(src_of(x, SR * 5), SR, 1, tmp_path / "a.wav")
    master(src_of(x, 12345), SR, 1, tmp_path / "b.wav")
    ya, yb = read(tmp_path / "a.wav")[0], read(tmp_path / "b.wav")[0]
    assert np.abs(ya - yb).max() < 1e-6


def test_master_silence_and_short_input(tmp_path):
    rep = master(src_of(np.zeros(3 * SR)), SR, 2 - 1, tmp_path / "s.wav")
    y = read(tmp_path / "s.wav")[0]
    assert len(y) == 3 * SR and not y.any()
    d = rep.to_dict()
    assert d["input_lufs"] is None and d["output_lufs"] is None
    rep = master(src_of(np.full(100, 0.5)), SR, 1, tmp_path / "t.wav")   # < one block
    assert len(read(tmp_path / "t.wav")[0]) == 100


def test_highpass_removes_rumble(tmp_path):
    t = np.arange(10 * SR) / SR
    x = speech_like(10) + 0.3 * np.sin(2 * np.pi * 25 * t)
    master(src_of(x), SR, 1, tmp_path / "m.wav")
    y = read(tmp_path / "m.wav")[0][:, 0]
    spec = lambda s: np.abs(np.fft.rfft(s[SR:9 * SR]))              # noqa: E731
    f = np.fft.rfftfreq(8 * SR, 1 / SR)
    band = (f > 24) & (f < 26)
    ratio_in = spec(x)[band].max() / spec(x)[(f > 300) & (f < 3000)].mean()
    ratio_out = spec(y)[band].max() / spec(y)[(f > 300) & (f < 3000)].mean()
    assert ratio_out < ratio_in / 10                      # >= 20 dB less rumble


def test_settings_target_is_respected(tmp_path):
    x = speech_like(30, seed=2)
    rep = master(src_of(x), SR, 1, tmp_path / "m.wav", MasterSettings(target_lufs=-19.0))
    assert rep.output_lufs == pytest.approx(-19.0, abs=0.3)


# ------------------------------------------------------------------ export

def test_timeline_source_does_not_soft_clip(tone_media, pool_of):
    m = tone_media("A", 8000 * 2, amp=0.8)
    tl = add_source_clip(new_timeline(8000, ["A"]), "A", m)
    tl = SetTrackGain("A", 7.0).apply(tl)
    y = np.concatenate(list(timeline_source(pool_of(m), tl, 1)()))
    assert np.abs(y).max() > 1.5                           # raw mix; the master does peak control


@needs_ffmpeg
def test_export_wav_and_mp3(tmp_path):
    x = speech_like(30) * 3
    seen = []
    res = export(src_of(np.stack([x, x], 1)), SR, 2, tmp_path / "out", "EP_测试", total=len(x),
                 tags={"title": "测试集", "artist": "洛城二三事"}, progress=lambda f, s: seen.append(f))
    assert set(res.files) == {"wav", "mp3"} and not res.errors
    # LAME low-passes ~17 kHz; this noise-based test signal has more HF than voices do
    assert res.mp3["lufs"] == pytest.approx(-16.0, abs=0.8)
    assert res.mp3["true_peak_db"] <= -0.5
    assert seen == sorted(seen) and seen[-1] == 1.0
    probe = subprocess.run([FFMPEG, "-hide_banner", "-i", res.files["mp3"]], capture_output=True,
                           text=True, encoding="utf-8").stderr
    assert "测试集" in probe and "洛城二三事" in probe and "128 kb/s" in probe
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["EP_测试.mp3", "EP_测试.wav"]


@needs_ffmpeg
def test_export_mp3_only_leaves_no_wav(tmp_path):
    res = export(src_of(speech_like(5)), SR, 1, tmp_path, "x", formats=("mp3",))
    assert list(res.files) == ["mp3"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["x.mp3"]


def test_export_without_ffmpeg_keeps_wav_and_reports(tmp_path, monkeypatch):
    monkeypatch.setattr(export_mod, "find_ffmpeg", lambda: None)
    res = export(src_of(speech_like(5)), SR, 1, tmp_path, "x")
    assert list(res.files) == ["wav"] and "ffmpeg" in res.errors["mp3"]
    with pytest.raises(export_mod.ExportError):
        export(src_of(speech_like(1)), SR, 1, tmp_path, "y", formats=("flac",))
