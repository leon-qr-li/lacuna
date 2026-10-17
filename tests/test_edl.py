import json

import pytest

from lacuna_core import (AddDuck, CutRange, EDLError, InsertClip, LiftRange, Op, Project,
                         SetClipGain, SetFades, SetRoomTone, SetTrackGain, SlipRegion, Timeline,
                         TrimClip, add_source_clip, new_timeline, to_samples, to_seconds, validate)
from lacuna_core.edl import Clip, canonical_json

SR = 8000


@pytest.fixture
def two_tracks(ramp_media):
    a = ramp_media("A", 10 * SR)
    b = ramp_media("B", 10 * SR, offset=500_000)
    tl = new_timeline(SR, ["A", "B"])
    tl = add_source_clip(tl, "A", a)
    tl = add_source_clip(tl, "B", b)
    return {a.media_id: a, b.media_id: b}, tl, a, b


def src_at(tl, track, t):
    """Source (media, sample) playing at timeline t on a track, or None in a gap."""
    for c in tl.track(track).clips:
        if c.start <= t < c.end:
            return c.media_id, c.src_in + t - c.start
    return None


def test_time_arithmetic():
    assert to_samples(1.0, 44100) == 44100
    assert to_samples(0.4, 44100) == 17640
    assert to_samples(1e-6, 44100) == 0
    assert to_seconds(22050, 44100) == 0.5
    assert all(to_samples(to_seconds(n, 48000), 48000) == n for n in (0, 1, 47999, 10**9))


def test_cut_all_tracks_ripples(two_tracks):
    media, tl, a, b = two_tracks
    tl2 = CutRange(SR, 3 * SR).apply(tl)
    validate(tl2, media)
    assert tl2.length == 8 * SR
    assert src_at(tl2, "A", SR - 1) == (a.media_id, SR - 1)
    assert src_at(tl2, "A", SR) == (a.media_id, 3 * SR)
    assert src_at(tl2, "B", SR) == (b.media_id, 3 * SR)
    assert tl.length == 10 * SR          # original untouched (immutable)


def test_single_track_cut_retimes_only_that_track(two_tracks):
    media, tl, a, b = two_tracks
    tl2 = CutRange(2 * SR, 2 * SR + 400, tracks=("B",)).apply(tl)
    validate(tl2, media)
    assert src_at(tl2, "A", 5 * SR) == (a.media_id, 5 * SR)
    assert src_at(tl2, "B", 5 * SR) == (b.media_id, 5 * SR + 400)
    assert tl2.track("B").end == 10 * SR - 400


def test_lift_leaves_gap_on_one_track(two_tracks):
    media, tl, a, _ = two_tracks
    tl2 = LiftRange("A", 1000, 1500).apply(tl)
    validate(tl2, media)
    assert src_at(tl2, "A", 999) == (a.media_id, 999)
    assert src_at(tl2, "A", 1000) is None and src_at(tl2, "A", 1499) is None
    assert src_at(tl2, "A", 1500) == (a.media_id, 1500)
    assert len(tl2.track("B").clips) == 1


def test_slip_moves_region_and_overwrites_destination(two_tracks):
    media, tl, _, b = two_tracks
    tl2 = SlipRegion("B", 1000, 1200, 300).apply(tl)
    validate(tl2, media)
    assert src_at(tl2, "B", 1000) is None and src_at(tl2, "B", 1199) is None   # vacated
    assert src_at(tl2, "B", 1200) == (b.media_id, 1200)                        # kept
    assert src_at(tl2, "B", 1300) == (b.media_id, 1000)                        # moved
    assert src_at(tl2, "B", 1499) == (b.media_id, 1199)
    assert src_at(tl2, "B", 1500) == (b.media_id, 1500)                        # untouched after
    assert sum(c.length for c in tl2.track("B").clips) == 10 * SR - 200
    with pytest.raises(EDLError):
        SlipRegion("B", 100, 200, -150).apply(tl)


def test_trim_and_validation(two_tracks):
    media, tl, a, _ = two_tracks
    tl = LiftRange("A", 4000, 6000).apply(tl)
    left = tl.track("A").clips[0]
    tl2 = TrimClip(left.id, "out", -500).apply(tl)
    validate(tl2, media)
    assert tl2.track("A").clips[0].end == 3500
    right = tl.track("A").clips[1]
    tl3 = TrimClip(right.id, "in", -1000).apply(tl)       # extend back into the gap
    validate(tl3, media)
    assert src_at(tl3, "A", 5000) == (a.media_id, 5000)
    with pytest.raises(EDLError):                          # overlap with left clip
        validate(TrimClip(right.id, "in", -3000).apply(tl), media)
    with pytest.raises(EDLError):                          # beyond source end
        validate(TrimClip(right.id, "out", 1).apply(tl), media)


def test_validation_rejects_bad_timelines(two_tracks):
    media, tl, a, _ = two_tracks
    tr = tl.track("A")
    bad = [
        tl.with_track(tr.__class__("A", (Clip("x", a.media_id, 0, 100, 0), Clip("y", a.media_id, 0, 100, 50)))),
        tl.with_track(tr.__class__("A", (Clip("x", "sha256:nope", 0, 100, 0),))),
        tl.with_track(tr.__class__("A", (Clip("x", a.media_id, -5, 100, 0),))),
        tl.with_track(tr.__class__("A", (Clip("x", a.media_id, 0, 100, -1),))),
        tl.with_track(tr.__class__("A", (Clip("x", a.media_id, 0, 100, 0, fade_in=80, fade_out=80),))),
    ]
    for t in bad:
        with pytest.raises(EDLError):
            validate(t, media)


def test_insert_with_ripple_pushes_all_tracks(two_tracks, ramp_media):
    media, tl, a, b = two_tracks
    music = ramp_media("M", SR, offset=900_000)
    media[music.media_id] = music
    tl2 = InsertClip("A", music.media_id, 0, SR, at=2 * SR, ripple=True).apply(tl)
    tl2 = AddDuck("B", 0, SR, 6.0, 80).apply(tl2)
    validate(tl2, media)
    assert src_at(tl2, "A", 2 * SR) == (music.media_id, 0)
    assert src_at(tl2, "A", 3 * SR) == (a.media_id, 2 * SR)
    assert src_at(tl2, "B", 2 * SR) is None
    assert src_at(tl2, "B", 3 * SR) == (b.media_id, 2 * SR)
    assert tl2.length == 11 * SR


def test_project_undo_redo_and_append_only_log(two_tracks):
    media, tl, *_ = two_tracks
    p = Project(media, tl)
    v0 = p.timeline
    p.apply(CutRange(100, 200))
    v1 = p.timeline
    p.apply(SetTrackGain("A", 7.0))
    assert p.timeline.track("A").gain_db == 7.0
    p.undo()
    assert p.timeline == v1
    p.undo()
    assert p.timeline == v0
    p.redo()
    assert p.timeline == v1
    p.apply(LiftRange("B", 0, 50))          # new branch drops the redo stack
    with pytest.raises(EDLError):
        p.redo()
    assert [e["action"] for e in p.log] == ["apply", "apply", "undo", "undo", "redo", "apply"]
    assert [e["seq"] for e in p.log] == list(range(6))
    assert p.at_version(2).track("A").gain_db == 7.0
    assert p.at_version(4) == v0
    with pytest.raises(EDLError):           # invalid op is rejected and not logged
        p.apply(SlipRegion("B", 0, 10, -100))
    assert p.version == 6


def test_json_roundtrip_is_lossless(two_tracks, noise_media):
    media, tl, a, _ = two_tracks
    room = noise_media("room", SR)
    media[room.media_id] = room
    p = Project(media, tl)
    p.apply(CutRange(10, 20, tracks=("A",)))
    p.apply(SlipRegion("B", 100, 300, 50))
    p.apply(AddDuck("A", 0, 100, 3.0, 10))
    p.apply(SetRoomTone("A", room.media_id, 0, SR, -3.0))
    cid = p.timeline.track("A").clips[0].id
    p.apply(SetClipGain(cid, -2.0))
    p.apply(SetFades(cid, 5, 5))
    p.undo()
    s = p.to_json()
    q = Project.from_json(s)
    assert q.timeline == p.timeline
    assert q.timeline.digest() == p.timeline.digest()
    assert q.to_json() == s
    assert Timeline.from_dict(json.loads(canonical_json(p.timeline.to_dict()))) == p.timeline
    for op in p.ops:
        assert Op.from_dict(json.loads(json.dumps(op.to_dict()))) == op


def test_no_op_can_create_audio_outside_sources(two_tracks):
    """Every clip in any reachable timeline references a registered source range."""
    media, tl, *_ = two_tracks
    p = Project(media, tl)
    for op in [CutRange(0, 10), SlipRegion("A", 50, 90, 1000), LiftRange("B", 3, 9),
               InsertClip("B", next(iter(media)), 0, 10, 100_000)]:
        p.apply(op)
        assert p.timeline.track("A").clips  # still referencing sources
        for tr in p.timeline.tracks:
            for c in tr.clips:
                m = media[c.media_id]
                assert 0 <= c.src_in < c.src_out <= m.frames


def test_insert_overlapping_existing_material_is_rejected(two_tracks):
    media, tl, a, _ = two_tracks
    with pytest.raises(EDLError):
        Project(media, tl).apply(InsertClip("B", a.media_id, 0, 10, 20_000))


# ---------------------------------------------------------------- batch application

def _shape(tl):
    """Everything that affects rendering (clip ids excluded: they only name pieces)."""
    return [(t.name, t.gain_db, t.ducks, [(c.media_id, c.src_in, c.src_out, c.start, c.gain_db, c.fade_in, c.fade_out)
                                          for c in t.clips]) for t in tl.tracks]


@pytest.mark.parametrize("seed", range(25))
def test_apply_batch_equals_sequential(two_tracks, seed):
    """Random episode-style op lists (gains, slips, lifts, latest-first non-overlapping cuts,
    some on a track subset) give the same timeline batched as applied one by one."""
    import random
    from lacuna_core import apply_batch
    rnd = random.Random(seed)
    media, tl, a, b = two_tracks
    tl = AddDuck("A", 3 * SR, 5 * SR, -6.0, 100).apply(tl)
    tl = SetFades(tl.track("B").clips[0].id, 40, 40).apply(tl)
    n = 10 * SR
    ops = [SetTrackGain("B", rnd.uniform(-3, 3))]
    for _ in range(rnd.randint(0, 3)):
        s = rnd.randrange(n - 2000)
        ops.append(SlipRegion(rnd.choice("AB"), s, s + rnd.randint(1, 800), rnd.randint(-500, 500)))
    for _ in range(rnd.randint(0, 40)):
        s = rnd.randrange(n - 1000)
        ops.append(LiftRange(rnd.choice("AB"), s, s + rnd.randint(1, 900)))
    pts = sorted(rnd.sample(range(n), 2 * rnd.randint(1, 30)))
    cuts = [(pts[i], pts[i + 1]) for i in range(0, len(pts), 2) if pts[i + 1] > pts[i]]
    for s, e in sorted(cuts, reverse=True):
        ops.append(CutRange(s, e, rnd.choice([None, None, ("A",), ("B",)])))
    seq = tl
    for o in ops:
        seq = o.apply(seq)
    fast = apply_batch(tl, ops)
    validate(fast, media)
    assert _shape(fast) == _shape(seq)
    assert fast.length == seq.length


def test_apply_batch_rejects_like_sequential(two_tracks):
    from lacuna_core import apply_batch
    media, tl, a, b = two_tracks
    with pytest.raises(EDLError):
        apply_batch(tl, [LiftRange("A", 10, 10)])
    with pytest.raises(EDLError):
        apply_batch(tl, [CutRange(10, 5)])
    with pytest.raises(EDLError):
        apply_batch(tl, [CutRange(10, 20, ("Z",))])
