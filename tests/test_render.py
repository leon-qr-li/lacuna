import hashlib

import numpy as np
import pytest
import soundfile as sf

from lacuna_core import (AddDuck, CutRange, LiftRange, RenderSettings, RenderStats, Renderer,
                         SetRoomTone, SetTrackGain, SlipRegion, add_source_clip, check_seams,
                         new_timeline, seams)
from lacuna_core.edl import Clip, Track, replace

SR = 8000
HARD = RenderSettings(xfade_ms=0, ceiling_db=0.0, limit_db=0.0)


def idx(y):
    """Recover source sample indices from a ramp-media render."""
    return np.rint(np.asarray(y).reshape(-1) * 1e6).astype(np.int64)


def test_exact_sample_placement(ramp_media, pool_of):
    m = ramp_media("A", 5000)
    tl = new_timeline(SR, ["A"])
    tl = tl.with_track(Track("A", (Clip("c", m.media_id, 1000, 2000, 100),)))
    y = Renderer(pool_of(m), HARD).render(tl, 0, 1200)
    assert y.shape == (1200, 1)
    assert np.all(y[:100] == 0) and np.all(y[1100:] == 0)
    assert np.array_equal(idx(y[100:1100]), np.arange(1000, 2000))


def test_cut_lands_on_exact_samples(ramp_media, pool_of):
    m = ramp_media("A", 20000)
    tl = add_source_clip(new_timeline(SR, ["A"]), "A", m)
    tl = CutRange(3000, 3500).apply(tl)
    y = idx(Renderer(pool_of(m), HARD).render(tl, 2990, 3010))
    assert list(y) == list(range(2990, 3000)) + list(range(3500, 3510))


def test_chunked_equals_one_shot_and_is_deterministic(tone_media, noise_media, pool_of, tmp_path):
    a, b = tone_media("A", 4 * SR, 230), tone_media("B", 4 * SR, 310)
    room = noise_media("room", SR)
    tl = new_timeline(SR, ["A", "B"])
    tl = add_source_clip(add_source_clip(tl, "A", a), "B", b)
    for op in (CutRange(5000, 7000), LiftRange("B", 9000, 12000), SlipRegion("A", 15000, 16000, 800),
               AddDuck("B", 1000, 4000, 6, 400), SetRoomTone("B", room.media_id, 0, SR)):
        tl = op.apply(tl)
    pool = pool_of(a, b, room)
    whole = Renderer(pool, RenderSettings(chunk_s=100)).render(tl, 0, tl.length)
    digests = []
    for chunk_s in (0.37, 1.0):
        r = Renderer(pool, RenderSettings(chunk_s=chunk_s))
        out = tmp_path / f"r{chunk_s}.wav"
        r.render_to_file(tl, out, subtype="FLOAT")
        y, sr = sf.read(out, dtype="float32", always_2d=True)
        assert sr == SR and len(y) == tl.length
        assert np.array_equal(y, whole)
        digests.append(hashlib.sha256(y.tobytes()).hexdigest())
    assert digests[0] == digests[1]


def test_seam_crossfade_removes_click(tone_media, pool_of):
    m = tone_media("A", 4 * SR, 200, amp=0.5)
    tl = add_source_clip(new_timeline(SR, ["A"]), "A", m)
    tl = CutRange(SR + 7, SR + 1107).apply(tl)    # joins +0.89 to -0.89 of the sine
    pool = pool_of(m)
    hard = Renderer(pool, HARD).render(tl, 0, 2 * SR)
    soft = Renderer(pool, RenderSettings(xfade_ms=16)).render(tl, 0, 2 * SR)
    joins = [x for x in seams(tl) if x.kind == "join"]
    [h] = check_seams(hard, SR, joins)
    [s] = check_seams(soft, SR, joins)
    assert h.click and not s.click
    assert s.delta_ratio < 1.5
    # away from the seam the crossfaded render is the untouched source
    assert np.array_equal(soft[200: SR - 100], hard[200: SR - 100])   # (t=0 has a fade-in)
    assert np.array_equal(soft[SR + 100:], hard[SR + 100:])


def test_equal_power_crossfade_keeps_level(noise_media, pool_of):
    a, b = noise_media("A", SR, amp=0.1, seed=1), noise_media("B", SR, amp=0.1, seed=2)
    tl = new_timeline(SR, ["T"]).with_track(Track("T", (
        Clip("a", a.media_id, 0, 4000, 0), Clip("b", b.media_id, 4000, 8000, 4000))))
    y = Renderer(pool_of(a, b), RenderSettings(xfade_ms=40)).render(tl, 0, 8000)[:, 0]
    seam_rms = np.sqrt(np.mean(y[4000 - 160:4000 + 160] ** 2))
    ref_rms = np.sqrt(np.mean(y[1000:3000] ** 2))
    assert abs(20 * np.log10(seam_rms / ref_rms)) < 1.0


def test_contiguous_split_is_not_a_seam(ramp_media, pool_of):
    m = ramp_media("A", 6000)
    one = new_timeline(SR, ["A"]).with_track(Track("A", (Clip("c", m.media_id, 0, 6000, 0),)))
    two = one.with_track(Track("A", (Clip("c", m.media_id, 0, 2500, 0), Clip("d", m.media_id, 2500, 6000, 2500))))
    r = Renderer(pool_of(m), RenderSettings(xfade_ms=16, ceiling_db=0, limit_db=0))
    assert np.array_equal(r.render(one, 0, 6000), r.render(two, 0, 6000))
    assert seams(two) == seams(one)


def test_gain_change_on_same_source_uses_linear_ramp(tone_media, pool_of):
    m = tone_media("A", SR, 200, amp=0.3)
    tl = new_timeline(SR, ["A"]).with_track(Track("A", (
        Clip("c", m.media_id, 0, 4000, 0), Clip("d", m.media_id, 4000, 8000, 4000, gain_db=-6.0))))
    y = Renderer(pool_of(m), RenderSettings(xfade_ms=20)).render(tl, 0, 8000)[:, 0]
    x = sf.read(m.path, dtype="float32")[0]
    g = 10 ** (-6 / 20)
    ratio = y[3920:4080] / np.where(np.abs(x[3920:4080]) > 1e-3, x[3920:4080], np.nan)
    ok = ~np.isnan(ratio)
    assert np.all(ratio[ok] <= 1.0 + 1e-5) and np.all(ratio[ok] >= g - 1e-5)   # no +3 dB bump


def test_per_track_independence(tone_media, pool_of):
    a, b = tone_media("A", 3 * SR, 250), tone_media("B", 3 * SR, 330)
    tl = new_timeline(SR, ["A", "B"])
    tl = add_source_clip(add_source_clip(tl, "A", a), "B", b)
    r = Renderer(pool_of(a, b))
    before_a = r.render_track(tl, 0, 0, tl.length)
    tl2 = SlipRegion("B", 4000, 6000, 1500).apply(LiftRange("B", 100, 900).apply(tl))
    assert np.array_equal(r.render_track(tl2, 0, 0, tl.length), before_a)
    assert not np.array_equal(r.render_track(tl2, 1, 0, tl.length), r.render_track(tl, 1, 0, tl.length))


def test_peak_safety_soft_clips(tone_media, pool_of):
    m = tone_media("A", SR, 100, amp=0.9)
    tl = SetTrackGain("A", 12.0).apply(add_source_clip(new_timeline(SR, ["A"]), "A", m))
    stats = RenderStats()
    y = Renderer(pool_of(m)).render(tl, 0, SR, stats)
    assert np.abs(y).max() <= 10 ** (-0.1 / 20) + 1e-6
    assert stats.peak > 3.0 and stats.limited > 0
    soft = tone_media("B", SR, 100, amp=0.85)                    # below the -1 dBFS knee
    quiet = add_source_clip(new_timeline(SR, ["A"]), "A", soft)
    q = Renderer(pool_of(soft), RenderSettings(xfade_ms=0)).render(quiet, 0, SR)
    assert np.array_equal(q[:, 0], sf.read(soft.path, dtype="float32")[0])


def test_room_tone_fills_interior_gaps_only(tone_media, noise_media, pool_of):
    m = tone_media("A", 2 * SR, 200)
    room = noise_media("room", SR // 2, amp=0.01)
    tl = add_source_clip(new_timeline(SR, ["A"]), "A", m, start=1000)
    tl = LiftRange("A", 6000, 10000).apply(tl)
    tl = SetRoomTone("A", room.media_id, 0, SR // 2).apply(tl)
    y = Renderer(pool_of(m, room)).render(tl, 0, tl.length + 2000)[:, 0]
    gap = y[6500:9500]
    assert 0.7 < np.sqrt(np.mean(gap ** 2)) / 0.01 < 1.3
    assert np.all(y[:900] == 0) and np.all(y[tl.length + 100:] == 0)   # no fill outside


def test_duck_and_stereo_pan(tone_media, pool_of):
    m = tone_media("A", SR, 200, amp=0.5)
    tl = add_source_clip(new_timeline(SR, ["A"]), "A", m)
    tl = AddDuck("A", 2000, 6000, 12.0, 400).apply(tl)
    tl = tl.with_track(replace(tl.tracks[0], pan=-1.0))
    y = Renderer(pool_of(m), RenderSettings(channels=2)).render(tl, 0, SR)
    assert y.shape == (SR, 2) and np.abs(y[:, 1]).max() < 1e-6
    lvl = lambda s: np.abs(y[s, 0]).max()
    assert abs(20 * np.log10(lvl(slice(3000, 5000)) / lvl(slice(500, 1500))) + 12) < 0.1
