import numpy as np
import pytest

from lacuna_core import (CutRange, LiftRange, Previewer, Project, RenderSettings, Renderer,
                         SegmentCache, SetTrackGain, add_source_clip, new_timeline, snap_cut,
                         snap_cut_media)

SR = 8000


def loud_with_valley(n, valley_at, valley_len, seed=0):
    x = 0.3 * np.random.default_rng(seed).standard_normal(n)
    x[valley_at:valley_at + valley_len] *= 0.001
    return x


def test_snap_finds_valley_within_radius():
    x = loud_with_valley(4000, 2080, 120)
    t = snap_cut([x], 2000, SR, radius_ms=150)
    assert 2080 <= t < 2200


def test_snap_ignores_valley_outside_radius():
    x = loud_with_valley(8000, 5000, 200)
    t = snap_cut([x], 2000, SR, radius_ms=150)
    assert abs(t - 2000) <= 150 * SR // 1000


def test_snap_needs_joint_valley_across_tracks():
    a = loud_with_valley(4000, 1900, 100, seed=1)       # A quiet early ...
    a[2150:2250] *= 0.001                                # ... and at 2150
    b = loud_with_valley(4000, 2150, 100, seed=2)        # B quiet only at 2150
    t = snap_cut([a, b], 2000, SR)
    assert 2150 <= t < 2250


def test_snap_lands_on_zero_crossing():
    tt = np.arange(4000) / SR
    x = 0.2 * np.sin(2 * np.pi * 150 * tt) * np.where((tt > 0.24) & (tt < 0.27), 0.05, 1.0)
    t = snap_cut([x], 2000, SR)
    assert 0.24 * SR <= t <= 0.27 * SR
    assert np.signbit(x[t]) != np.signbit(x[t - 1])


def test_snap_on_media(noise_media, pool_of, tmp_path):
    from tests.conftest import write
    x = loud_with_valley(SR, 4100, 200)
    m = write(tmp_path / "v.wav", x)
    t = snap_cut_media(pool_of(m), [m.media_id], 4000, SR)
    assert 4100 <= t < 4300


@pytest.fixture
def long_project(tone_media, noise_media):
    a = tone_media("A", 120 * SR, 210, amp=0.2)
    b = noise_media("B", 120 * SR, amp=0.05)
    tl = new_timeline(SR, ["A", "B"])
    tl = add_source_clip(add_source_clip(tl, "A", a), "B", b)
    return Project({a.media_id: a, b.media_id: b}, tl), a, b


def test_preview_matches_full_render_and_caches(long_project, pool_of):
    p, a, b = long_project
    r = Renderer(pool_of(a, b), RenderSettings())
    pv = Previewer(r, SegmentCache(), block_s=2.0)
    t = 60 * SR
    first = pv.around(p.timeline, t, ctx_s=10)
    assert first.rendered == first.blocks > 0
    assert len(first.audio) == 20 * SR
    assert np.array_equal(first.audio, r.render(p.timeline, t - 10 * SR, t + 10 * SR))
    again = pv.around(p.timeline, t, ctx_s=10)
    assert again.rendered == 0 and np.array_equal(again.audio, first.audio)

    p.apply(CutRange(100 * SR, 101 * SR))                 # downstream edit: window unaffected
    assert pv.around(p.timeline, t, ctx_s=10).rendered == 0

    p.apply(CutRange(10 * SR, 10 * SR + 1234))            # upstream cut shifts everything
    shifted = pv.around(p.timeline, t, ctx_s=10)
    assert shifted.rendered == shifted.blocks             # no stale blocks
    assert np.array_equal(shifted.audio, r.render(p.timeline, t - 10 * SR, t + 10 * SR))

    p.undo()                                              # back to cached state
    assert pv.around(p.timeline, t, ctx_s=10).rendered == 0


def test_local_edit_rerenders_only_touched_blocks(long_project, pool_of):
    p, a, b = long_project
    pv = Previewer(Renderer(pool_of(a, b)), block_s=2.0)
    t = 60 * SR
    pv.around(p.timeline, t, ctx_s=10)
    p.apply(LiftRange("B", 61 * SR + 100, 61 * SR + 900))   # inside one 2 s block
    res = pv.around(p.timeline, t, ctx_s=10)
    assert res.rendered == 1
    p.apply(SetTrackGain("A", 3.0))                          # global change: everything
    assert pv.around(p.timeline, t, ctx_s=10).rendered == 10


def test_ab_pair_and_latency(long_project, pool_of):
    p, a, b = long_project
    before = p.timeline
    p.apply(CutRange(50 * SR, 51 * SR))
    pv = Previewer(Renderer(pool_of(a, b)))
    ra, rb = pv.ab(before, p.timeline, 50 * SR, 50 * SR, ctx_s=10)
    assert len(ra.audio) == len(rb.audio) == 20 * SR
    assert ra.seconds < 3.0 and rb.seconds < 3.0


def test_cache_byte_budget_evicts_lru():
    c = SegmentCache(max_bytes=3 * 400)
    for i in range(5):
        c.put(str(i), np.zeros(100, np.float32))
    assert len(c) == 3 and c.get("0") is None and c.get("4") is not None


def test_cache_key_soundness_under_random_edits(tone_media, noise_media, pool_of):
    """Equal range keys must always mean bit-identical audio (no stale cache hits)."""
    from lacuna_core import AddDuck, SetRoomTone, SlipRegion
    a, b = tone_media("A", 30 * SR, 190, amp=0.2), noise_media("B", 30 * SR, amp=0.05)
    room = noise_media("R", SR, amp=0.002, seed=9)
    tl = new_timeline(SR, ["A", "B"])
    tl = add_source_clip(add_source_clip(tl, "A", a), "B", b)
    p = Project({m.media_id: m for m in (a, b, room)}, tl)
    r = Renderer(pool_of(a, b, room))
    rng = np.random.default_rng(42)
    seen: dict[str, np.ndarray] = {}
    blk = SR
    for step in range(25):
        s = int(rng.integers(0, 20 * SR))
        n = int(rng.integers(50, SR))
        op = [CutRange(s, s + n), CutRange(s, s + n, tracks=("B",)), LiftRange("A", s, s + n),
              SlipRegion("B", s, s + n, int(rng.integers(-40, 400))),
              AddDuck("A", s, s + n, 6.0, 100),
              SetRoomTone("A", room.media_id, 0, SR)][step % 6]
        try:
            p.apply(op)
        except ValueError:
            continue
        for k in range(0, p.timeline.length, blk):
            key = r.range_key(p.timeline, k, k + blk)
            y = r.render(p.timeline, k, k + blk)
            if key in seen:
                assert np.array_equal(seen[key], y)
            seen[key] = y
    assert len(seen) > 100
