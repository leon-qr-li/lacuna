"""Single-track erase filled with room tone (backlog item 8): the core op and the tone picker."""
import numpy as np
import pytest

from lacuna_core import EDLError, EraseRange, LiftRange, Op, Renderer, RenderSettings, add_source_clip, apply_batch, \
    new_timeline, validate
from lacuna_app import room_tone

SR = 8000


def test_erase_fills_only_where_the_track_had_material(ramp_media, pool_of):
    m = ramp_media("A", 20000)
    tl = add_source_clip(new_timeline(SR, ["A", "B"]), "A", m, src_out=10000)
    op = EraseRange("A", 3000, 12000, m.media_id, 15000, 15800)      # runs past the clip's end at 10000
    out = op.apply(tl)
    validate(out, {m.media_id: m})
    clips = out.track("A").clips
    assert out.length == tl.length                                   # the track never grows
    fill = [c for c in clips if c.media_id == m.media_id and c.src_in == 15000]
    assert [c.start for c in fill] == list(range(3000, 10000, 800))  # tiled 800-sample tone
    assert sum(c.length for c in fill) == 7000
    assert clips[0].end == 3000 and out.track("B") == tl.track("B")
    # no ripple: the samples before the erase are untouched
    y = Renderer(pool_of(m), RenderSettings(xfade_ms=0, ceiling_db=0, limit_db=0)).render(out, 0, 3000)
    assert np.array_equal(np.rint(y[:, 0] * 1e6).astype(int), np.arange(3000))


def test_erase_without_tone_is_a_lift_and_round_trips(ramp_media):
    m = ramp_media("A", 20000)
    tl = add_source_clip(new_timeline(SR, ["A"]), "A", m)
    plain = EraseRange("A", 3000, 4000)
    assert plain.apply(tl).track("A").clips == LiftRange("A", 3000, 4000).apply(tl).track("A").clips
    op = EraseRange("A", 3000, 4000, m.media_id, 100, 500)
    assert Op.from_dict(op.to_dict()) == op and op.to_dict()["op"] == "erase"
    # batch application (episode path) gives the same timeline
    lifts = [LiftRange("A", 1000, 1500), op, LiftRange("A", 6000, 6100)]
    seq = tl
    for o in lifts:
        seq = o.apply(seq)
    strip = lambda clips: [c.__class__(**{**c.__dict__, "id": ""}) for c in clips]  # noqa: E731  ids may differ
    assert strip(apply_batch(tl, lifts).track("A").clips) == strip(seq.track("A").clips)
    with pytest.raises(EDLError):
        EraseRange("A", 4000, 4000).apply(tl)
    with pytest.raises(EDLError):
        EraseRange("A", 3000, 4000, m.media_id, 500, 500).apply(tl)


def test_erased_span_sounds_like_the_room_not_silence(tmp_path, pool_of):
    from tests.conftest import write
    rng = np.random.default_rng(1)
    n = 10 * SR
    x = 0.002 * rng.standard_normal(n)                               # the room
    k = int(0.9 * SR)
    x[int(4.05 * SR):int(4.05 * SR) + k] += 0.3 * np.sin(2 * np.pi * 200 * np.arange(k) / SR)   # a 嗯; the erase
    # range is padded past it, as the chat (±30 ms) and the first cut (snapped to quiet) do
    m = write(tmp_path / "pei.wav", x)
    tl = add_source_clip(new_timeline(SR, ["Pei"]), "Pei", m)
    op = room_tone.resolve({"op": "erase", "track": "Pei", "start": 4 * SR, "end": 5 * SR}, tl, pool_of(m))
    assert op["tone_media_id"] == m.media_id
    assert not (op["tone_src_in"] < 5.3 * SR and op["tone_src_out"] > 3.7 * SR)   # not the 嗯 itself
    out = Op.from_dict(op)
    y = Renderer(pool_of(m)).render(out.apply(tl), 4 * SR, 5 * SR)[:, 0]
    rms = float(np.sqrt(np.mean(y ** 2)))
    assert 0.0015 < rms < 0.003                                       # room level, no 嗯, no hole
    lifted = Renderer(pool_of(m)).render(LiftRange("Pei", 4 * SR, 5 * SR).apply(tl), 4 * SR + 200, 5 * SR - 200)
    assert np.max(np.abs(lifted)) == 0                                # what Leon heard before


def test_pick_avoids_words_transients_and_digital_silence():
    sr = 8000
    rng = np.random.default_rng(2)
    x = 0.003 * rng.standard_normal(20 * sr)
    x[:3 * sr] = 0.0                                                  # digital silence: never room tone
    x[8 * sr:8 * sr + 40] += 0.5                                      # a click at 8 s
    x[14 * sr:16 * sr] *= 0.3                                         # quietest room, but a word sits there
    words = [(14.5, 15.5)]
    at = room_tone.pick(x, sr, 0, 10 * sr, 11 * sr, sr, words)
    assert at is not None
    a, b = at / sr, at / sr + 1
    assert a >= 3 and not (a < 8.01 and b > 8)                        # no silence, no click
    assert not (a < 11.3 and b > 9.7) and not (a < 15.62 and b > 14.38)
    assert room_tone.pick(np.zeros(5 * sr), sr, 0, 2 * sr, 3 * sr, sr) is None
    assert room_tone.tone_length(sr // 10, sr) == int(0.3 * sr) and room_tone.tone_length(9 * sr, sr) == int(1.5 * sr)
