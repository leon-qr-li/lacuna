"""Clipping repair (lacuna_core/declip.py, 验收 V7): what is found, what is rebuilt, what is left alone."""
import numpy as np
import pytest
import soundfile as sf
from scipy.signal import lfilter, stft

from lacuna_core import MediaRef, Renderer, RenderSettings, SourcePool, add_source_clip, new_timeline
from lacuna_core import declip

SR = 44100


def voice(seconds: float, f0: float = 140.0, seed: int = 0) -> np.ndarray:
    """Voiced, speech-like signal (glottal pulses through three formants, syllable envelope), peak 1."""
    r = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    ph = np.cumsum(f0 * (1 + 0.1 * np.sin(2 * np.pi * 0.7 * t)) / SR)
    y = lfilter([1], [1, -0.97], np.diff(np.floor(ph), prepend=0))
    for f, b in ((700, 90), (1200, 110), (2600, 160)):
        rr, th = np.exp(-np.pi * b / SR), 2 * np.pi * f / SR
        y = lfilter([1], [1, -2 * rr * np.cos(th), rr * rr], y)
    y = lfilter([1, -1], [1], y) * np.clip(np.sin(2 * np.pi * 2.5 * t), 0, None) ** 0.7
    y = y + 0.003 * r.standard_normal(n)
    return y / np.abs(y).max()


def s16(x: np.ndarray) -> np.ndarray:
    """What a 16-bit converter records: hard clip at full scale."""
    return (np.clip(np.round(x * 32767), -32768, 32767) / 32768).astype(np.float32)


def run(x: np.ndarray, **kw):
    return declip.scan(lambda a, b: x[a:b].copy(), len(x), SR, **kw)


def repaired(x: np.ndarray, p: declip.Patches) -> np.ndarray:
    return p.apply(0, x.copy())


def hf(y: np.ndarray) -> float:
    """Energy above 5 kHz, where clipping's harmonics land (the formants stop at 2.6 kHz)."""
    f, _, z = stft(y, SR, nperseg=1024)
    return float(np.abs(z[f > 5000]).sum())


@pytest.mark.parametrize("drive", [1.3, 1.6, 2.0])
def test_clipped_speech_is_rebuilt_and_never_louder_than_the_recording(drive):
    ref = voice(12) * drive * 0.95
    x = s16(ref)
    p, rep = run(x)
    assert rep.events > 10 and rep.repaired == rep.events and not rep.skipped
    y = repaired(x, p)
    # the harsh harmonics of the flattened peaks are gone (>= 20x less than clipped)
    assert hf(y) * 20 < hf(x)
    assert hf(y) < 4 * hf(s16(ref / drive))      # close to the same speech recorded without clipping
    # never louder than what was recorded: rebuilt peaks are brought back to the ceiling
    assert np.abs(y).max() <= np.abs(x).max() + 1e-6
    # only the neighbourhood of clipped samples changes; everything else is bit-identical
    hot = np.abs(x) >= np.abs(x).max() * (1 - declip.TOL)
    near = np.convolve(hot, np.ones(2 * int(declip.RELEASE_S * SR) + 1), "same") > 0
    assert np.array_equal(y[~near], x[~near])


def test_clean_recordings_are_left_alone():
    for g in (0.99, 0.95, 0.5, 1.0):
        x = s16(voice(8) * g)
        p, rep = run(x)
        assert rep.events == 0 and len(p) == 0 and rep.ceiling == (0.0, 0.0)


def test_full_scale_tones_come_through_unchanged():
    """A pure tone at full scale is not clipped; whatever the scan does with it stays under 1 LSB."""
    t = np.arange(3 * SR) / SR
    for f in (60, 100, 300, 1000):
        x = s16(np.sin(2 * np.pi * f * t))
        p, _ = run(x)
        assert np.abs(repaired(x, p) - x).max() < 1 / 32768


def test_clipping_resampled_afterwards_is_still_found():
    """Recorded at 48 kHz, clipped, then converted to 44.1 kHz: the plateaus ripple instead of
    staying perfectly flat, but they still crowd the ceiling."""
    from scipy.signal import resample_poly
    ref = voice(10, f0=200) * 1.6
    x = s16(resample_poly(resample_poly(np.clip(ref, -1, 1), 160, 147), 147, 160) * 0.97)
    p, rep = run(x)
    assert rep.events > 10 and rep.repaired >= 0.9 * rep.events
    assert hf(repaired(x, p)) * 10 < hf(x)


def test_silence_and_quiet_files():
    for x in (np.zeros(SR, np.float32), s16(voice(3) * 0.1)):
        p, rep = run(x)
        assert rep.events == 0 and len(p) == 0


def test_clipping_below_full_scale_is_found():
    """A recording clipped and then turned down (or normalised) still has flat tops, just lower."""
    x = (s16(voice(8) * 1.5) * 0.7).astype(np.float32)
    p, rep = run(x)
    assert rep.events > 5 and rep.repaired == rep.events
    assert max(rep.ceiling) == pytest.approx(0.7, abs=0.01)
    assert hf(repaired(x, p)) * 10 < hf(x)


def test_long_flat_runs_are_left_as_recorded():
    """A shout pinned at the ceiling for 10 ms: the wave under it is unknowable, so no guess."""
    x = s16(voice(6) * 0.5)
    for t in (1.03, 3.03):
        i = int(t * SR)
        x[i:i + 441] = 1.0
    p, rep = run(x)
    assert rep.events == 2 and rep.repaired == 0 and rep.skipped == {declip.SKIP_LONG: 2}
    assert [s / SR for s in rep.skipped_at] == pytest.approx([1.03, 3.03], abs=1e-3)
    assert np.array_equal(repaired(x, p), x)


def test_runs_across_scan_blocks_are_seen_whole():
    ref = voice(10) * 1.6
    x = s16(ref)
    p1, r1 = run(x)
    p2, r2 = run(x, block_s=0.37)          # block edges land inside clipped runs
    assert (r1.events, r1.repaired, r1.clipped_samples) == (r2.events, r2.repaired, r2.clipped_samples)
    assert np.allclose(repaired(x, p1), repaired(x, p2), atol=1e-6)


def test_patches_apply_the_same_in_any_chunking():
    x = s16(voice(5) * 1.8)
    p, _ = run(x)
    whole = repaired(x, p)
    for step in (7, 512, 44100):
        parts = [p.apply(s, x[s:s + step].copy()) for s in range(0, len(x), step)]
        assert np.array_equal(np.concatenate(parts), whole)
    assert p.digest() == declip.Patches.from_npz(p.to_npz()).digest()


def test_source_pool_overlays_repair_and_render_cache_keys_follow_it(tmp_path):
    x = s16(voice(4) * 1.6)
    path = tmp_path / "pei.wav"
    sf.write(path, x, SR, subtype="PCM_16")
    raw_bytes = path.read_bytes()
    ref = MediaRef.probe(path)
    p, _ = run(sf.read(path, dtype="float32")[0])
    fixed = MediaRef.probe(path, ref.media_id)
    from dataclasses import replace
    fixed = replace(fixed, patches=p)
    assert fixed == ref and fixed.to_dict() == ref.to_dict()      # the repair is never saved
    with SourcePool({ref.media_id: fixed}) as pool, SourcePool({ref.media_id: fixed}, repaired=False) as raw:
        a = pool.read(ref.media_id, 0, ref.frames)
        b = raw.read(ref.media_id, 0, ref.frames)
        assert np.array_equal(b, sf.read(path, dtype="float32")[0])
        assert np.array_equal(a, repaired(b, p)) and not np.array_equal(a, b)
        tl = add_source_clip(new_timeline(SR, ["Pei"]), "Pei", ref)
        m0, m1 = int(0.1 * SR), ref.frames - int(0.1 * SR)          # away from the clip's edge fades
        out = Renderer(pool, RenderSettings(ceiling_db=60, limit_db=60.1)).render(tl, m0, m1)[:, 0]
        assert np.allclose(out, a[m0:m1], atol=1e-6)
        k1 = Renderer(pool, RenderSettings()).range_key(tl, 0, ref.frames)
        k2 = Renderer(raw, RenderSettings()).range_key(tl, 0, ref.frames)
        assert k1 != k2                                              # no stale preview audio
    assert path.read_bytes() == raw_bytes                            # the recording is untouched
