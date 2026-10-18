"""Audio bugs found by the full scan of 2026-10-18 (room tone late in a track, short music stings)."""
import numpy as np
import pytest
import soundfile as sf

from lacuna_app import room_tone
from lacuna_app.episode import Episode, create_episode
from lacuna_app.library import Library
from lacuna_app.music import EpisodeMusic
from lacuna_app.store import Workspace
from lacuna_core import MediaRef, Project, SourcePool, add_source_clip, new_timeline

from .synth import EPISODE, SR, make_workspace, write_music

EP = "EP_scan"


def one_track_workspace(root, name, x):
    raw = root / "episodes" / EP / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    p = raw / f"{name}.wav"
    sf.write(p, x.astype(np.float32), SR, subtype="FLOAT")
    ref = MediaRef.probe(p)
    tl = add_source_clip(new_timeline(SR, [name]), name, ref)
    create_episode(Workspace(root), EP, {"title": "t", "demo": False, "raw_offset_s": 0.0},
                   Project({ref.media_id: ref}, tl), [], None)
    return Workspace(root)


def test_room_tone_for_an_erase_late_in_the_track_comes_from_near_it(tmp_path):
    """The tone position was returned relative to the search window (30 s before the erase), so
    any erase after the first 30 s filled the gap with audio from early in the track."""
    rng = np.random.default_rng(3)
    x = 0.2 * rng.standard_normal(120 * SR)                     # "speech" everywhere ...
    x[95 * SR:97 * SR] = 3e-4 * rng.standard_normal(2 * SR)     # ... except the room at 95-97 s
    ep = Episode(one_track_workspace(tmp_path, "Pei", x), EP)
    op = {"op": "erase", "track": "Pei", "start": 100 * SR, "end": int(100.5 * SR)}
    with SourcePool(ep.media) as pool:
        out = room_tone.resolve(op, ep.base, pool)
    assert 95.0 <= out["tone_src_in"] / SR and out["tone_src_out"] / SR <= 97.0


def test_a_music_sting_shorter_than_the_meter_window_is_still_levelled(tmp_path):
    """Loudness needs 0.4 s; a 0.3 s sting measured -inf and played at the file's raw level."""
    ws = Workspace(make_workspace(tmp_path / "ws"))
    lib = Library(ws)
    a = lib.add_file(write_music(tmp_path / "in" / "s.wav", 12.0, level=0.9), "interlude")
    m = EpisodeMusic(ws, Episode(ws, EPISODE), lib)
    m.add(a["id"], "bed", at_s=5.0, src_in_s=2.0, src_out_s=2.3)
    m.add(a["id"], "bed", at_s=20.0, src_in_s=2.0, src_out_s=3.0)
    short, longer = m.summary()["placements"]
    assert longer["level_db"] < -3
    assert short["level_db"] == pytest.approx(longer["level_db"], abs=1.0)


def test_episodes_with_a_pre_fix_room_tone_are_repaired_on_open(tmp_path):
    """Erases stored before the fix keep the wrong tone (resolve skips ops that already have one):
    Leon heard Pei's own deleted words from the first minute, looped three times, at 9:00
    (验收 V5). Opening the episode picks those tones again, near the erase, and saves them."""
    import json
    rng = np.random.default_rng(3)
    x = 0.2 * rng.standard_normal(120 * SR)
    x[95 * SR:97 * SR] = 3e-4 * rng.standard_normal(2 * SR)
    ws = one_track_workspace(tmp_path, "Pei", x)
    ep = Episode(ws, EP)
    media = next(iter(ep.media))
    bad = {"op": "erase", "track": "Pei", "start": 100 * SR, "end": int(100.5 * SR),
           "tone_media_id": media, "tone_src_in": 5 * SR, "tone_src_out": int(5.5 * SR)}   # old bug
    near = {**bad, "start": 20 * SR, "end": int(20.5 * SR)}                                # inside the window: kept
    assert room_tone.misplaced(bad, ep.base) and not room_tone.misplaced(near, ep.base)
    ep.close()
    p = ws.episode_dir(EP) / "state.json"
    st = json.loads(p.read_text(encoding="utf-8"))
    st["edits"] = [{"id": "e1", "ops": [bad], "category": "interjection", "title": "t", "reason": "",
                    "confidence": 0.9, "consequential": True, "status": "applied", "source": "ai"},
                   {"id": "e2", "ops": [near], "category": "interjection", "title": "t", "reason": "",
                    "confidence": 0.9, "consequential": True, "status": "applied", "source": "ai"}]
    p.write_text(json.dumps(st), encoding="utf-8")
    ep = Episode(ws, EP)
    fixed, kept = ep.edits["e1"].ops[0], ep.edits["e2"].ops[0]
    assert 95.0 <= fixed["tone_src_in"] / SR and fixed["tone_src_out"] / SR <= 97.0
    assert kept == near
    ep.close()
    saved = json.loads(p.read_text(encoding="utf-8"))["edits"][0]["ops"][0]
    assert saved["tone_src_in"] == fixed["tone_src_in"]
