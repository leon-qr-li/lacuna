"""Music page improvements (首次检测 15-22): automatic / looping beds, changing a placement's use,
the 22 dB background default and where listening to one placement starts."""
import json
import shutil

import pytest
from fastapi.testclient import TestClient
from pathlib import Path

from lacuna_app import create_app
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.episode import Episode
from lacuna_app.library import Library
from lacuna_app.music import BED_BG_DB, BG_DB, EpisodeMusic, layout, loop_passes
from lacuna_app.store import Workspace

from .synth import EPISODE, SR, make_workspace, write_music

R = 100   # samples per second in the pure layout tests


def song(aid: str, dur: float) -> dict:
    return {"id": aid, "duration_s": dur, "lufs": -14.0}


def place(pid: str, aid: str, role: str, **kw) -> dict:
    return {"id": pid, "asset_id": aid, "role": role, "status": "applied", **kw}


ASSETS = {a["id"]: a for a in (song("in", 20), song("mid", 30), song("out", 30), song("b1", 10), song("b2", 10),
                                song("b3", 10))}
BASE = [place("i", "in", "intro", solo_s=5, ramp_s=2),
        place("m", "mid", "interlude", at_base=50 * R, solo_s=15, ramp_s=2, ramp_out_s=2),
        place("o", "out", "outro", bye_s=10, ramp_s=2)]


def lay_of(ps):
    return layout(ps, ASSETS, R, 100 * R, lambda b: b)


def test_layout_free_stretches_for_automatic_beds():
    lay = lay_of(BASE)
    spans = {it.p["id"]: (it.start, it.end) for it in lay.items}
    # intro 0-20 s, interlude at 55 s for its 30 s, outro from 10 s before the talk ends (124 s)
    assert spans == {"i": (0, 2000), "m": (5500, 8500), "o": (11400, 14400)}

    lay = lay_of(BASE + [place("a", "b1", "bed", auto=True), place("b", "b2", "bed", auto=True, loop=True),
                         place("c", "b3", "bed", auto=True)])
    spans = {it.p["id"]: (it.start, it.end) for it in lay.items}
    assert spans["a"] == (2000, 3000)                     # the first free stretch, plays once
    assert spans["b"] == (3000, 5500)                     # loops to fill the rest of that stretch
    assert spans["c"] == (8500, 9500)                     # the next free stretch (after the interlude)
    b = next(it for it in lay.items if it.p["id"] == "b")
    assert b.period == 1000 and b.anchor == 3000
    assert not lay.unplaced


def test_no_room_and_short_stretches():
    full = [place("x", "mid", "bed", at_base=0, until_base=100 * R, loop=True)]   # a manual bed over the whole talk
    lay = lay_of(full + [place("a", "b1", "bed", auto=True)])
    assert [p["id"] for p in lay.unplaced] == ["a"] and len(lay.items) == 1
    # a stretch under 8 s is skipped
    ps = [place("i", "in", "intro", solo_s=5), place("x", "mid", "bed", at_base=int(21 * R), until_base=100 * R, loop=True),
          place("a", "b1", "bed", auto=True)]
    lay = lay_of(ps)       # free: 20-26 s only (the looping bed runs from 26 s to the end)
    assert [p["id"] for p in lay.unplaced] == ["a"]


def test_manual_looping_bed_fills_to_its_end_or_the_next_music():
    lay = lay_of(BASE + [place("l", "b1", "bed", at_base=20 * R, loop=True)])
    it = next(x for x in lay.items if x.p["id"] == "l")
    # from 25 s of the final mix up to where the interlude starts (55 s)
    assert (it.start, it.end, it.period) == (2500, 5500, 1000)
    lay = lay_of(BASE + [place("l", "b1", "bed", at_base=20 * R, until_base=40 * R, loop=True)])
    it = next(x for x in lay.items if x.p["id"] == "l")
    assert (it.start, it.end) == (2500, 4500)


def test_loop_passes_crossfade():
    # once: one pass, cut short
    assert loop_passes(0, 500, 0, 0, 10, 30, 20, 1000) == [(0, 500, 0, 10, 30)]
    ps = loop_passes(100, 2500, 0, 1000, 10, 30, 20, 1000)
    starts = [p[2] for p in ps]
    assert starts == [100, 1080, 2060]                     # each pass starts 20 samples before the last ends
    assert ps[0][3] == 10 and ps[1][3] == 20 and ps[-1][4] == 30
    assert ps[-1][2] + (ps[-1][1] - ps[-1][0]) == 100 + 2500
    assert all(a == 0 for a, *_ in ps)


# ------------------------------------------------------------------ with the real episode

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


@pytest.fixture
def setup(tmp_path):
    ws = Workspace(make_workspace(tmp_path / "ws"))
    lib = Library(ws)
    ep = Episode(ws, EPISODE)
    bed = lib.add_file(write_music(tmp_path / "in" / "bed.wav", 10.0), "bed")
    intro = lib.add_file(write_music(tmp_path / "in" / "intro.wav", 12.0), "intro")
    yield ws, lib, ep, bed, intro
    ep.close()


def test_automatic_looping_bed_mix(setup):
    ws, lib, ep, bed, intro = setup
    m = EpisodeMusic(ws, ep, lib)
    p = m.add(bed["id"], "bed", loop=True)
    assert p["auto"] is True and p["loop"] is True and p["at_base"] is None and p["bg_db"] == BED_BG_DB == 22.0   # 铺底 default (Leon 2026-10-31: back from 25)
    tl, media, lay = m.mix()
    it = next(x for x in lay.items if x.p["id"] == p["id"])
    assert it.start == 0 and it.length == lay.final(lay.voice_len)   # the whole talk is free: fills it
    tracks = [t for t in tl.tracks if p["id"] in t.name]
    assert len(tracks) == 2                                 # two tracks take turns, so passes overlap
    clips = sorted((c for t in tracks for c in t.clips), key=lambda c: c.start)
    assert len(clips) >= 3 and clips[0].start == 0
    for a, b in zip(clips, clips[1:]):
        assert b.start == a.start + a.length - 2 * SR       # 2 s crossfade
        assert a.fade_out == 2 * SR and b.fade_in == 2 * SR
    assert clips[-1].start + clips[-1].length == it.end and 0 < clips[-1].fade_out <= 3 * SR   # fades out at the end
    # stereo export: L and R for each of the two tracks
    tl2, _, _ = m.mix(channels=2)
    assert len([t for t in tl2.tracks if p["id"] in t.name]) == 4
    # with an intro, the bed starts where the intro has finished
    m.add(intro["id"], "intro")
    lay = m.layout()
    i, b = (next(x for x in lay.items if x.p["role"] == r) for r in ("intro", "bed"))
    assert b.start == i.end
    # a position makes it a bed at that point
    q = m.update(p["id"], at_s=5.0)
    assert q["auto"] is False and q["at_base"] is not None
    q = m.update(p["id"], auto=True)
    assert q["auto"] is True and q["until_base"] is None


def test_change_use_keeps_song_trim_volume(setup):
    ws, lib, ep, bed, intro = setup
    m = EpisodeMusic(ws, ep, lib)
    p = m.add(intro["id"], "intro", src_in_s=1.0, src_out_s=10.0, gain_db=-4.0, bg_db=18.0, solo_s=3.0, ramp_s=4.0)
    q = m.update(p["id"], role="outro")
    assert (q["role"], q["src_in_s"], q["src_out_s"], q["gain_db"], q["bg_db"]) == ("outro", 1.0, 10.0, -4.0, 18.0)
    assert q["solo_s"] is None and q["ramp_s"] == 2.0 and q["bye_s"] is not None   # the outro's own numbers, defaults
    q = m.update(p["id"], role="bed")                       # no position: placed automatically
    assert q["role"] == "bed" and q["auto"] is True and q["gain_db"] == -4.0
    q = m.update(p["id"], role="interlude", at_s=20.0)
    assert q["role"] == "interlude" and q["solo_s"] == 15.0 and q["auto"] is None and q["at_base"] is not None
    with pytest.raises(ValueError):
        m.update(m.add(intro["id"], "intro")["id"], role="clip")   # an interlude / clip needs a position


def test_saved_background_level_is_kept(setup):
    ws, lib, ep, bed, intro = setup
    m = EpisodeMusic(ws, ep, lib)
    p = m.add(intro["id"], "intro", bg_db=20.0)              # e.g. placed before the default became 22
    doc = json.loads(m.path.read_text("utf-8"))
    assert doc["placements"][0]["bg_db"] == 20.0
    assert m.update(p["id"], gain_db=-1.0)["bg_db"] == 20.0


def test_api_change_use_and_listen_point(tmp_path):
    ws = make_workspace(tmp_path / "ws")
    client = TestClient(create_app(ws, MockEditorAdapter(), web_dist=Path("/nonexistent")))
    path = write_music(tmp_path / "in" / "jingle.wav", 8.0)
    a = client.post("/api/library/upload", params={"name": "jingle.wav", "kind": "intro", "note": ""},
                    content=path.read_bytes(), headers={"Content-Type": "application/octet-stream"}).json()
    aid = a["asset"]["id"]
    ep = f"/api/episodes/{EPISODE}"
    m = client.post(f"{ep}/music", json={"asset_id": aid, "role": "intro"}).json()
    p = m["placements"][0]
    assert p["bg_db"] == 22.0 and p["listen_s"] == 0.0
    # intro -> interlude with no position: the App picks a pause in the talk
    m = client.patch(f"{ep}/music/{p['id']}", json={"role": "interlude"}).json()
    p = m["placements"][0]
    assert p["role"] == "interlude" and p["at_s"] > 0 and p["listen_s"] == pytest.approx(max(p["start_s"] - 5, 0), abs=0.01)
    # -> bed: automatic, loops on request
    m = client.patch(f"{ep}/music/{p['id']}", json={"role": "bed", "loop": True}).json()
    p = m["placements"][0]
    assert p["role"] == "bed" and p["loop"] is True and p["auto"] is False   # it kept the interlude's position
    m = client.patch(f"{ep}/music/{p['id']}", json={"auto": True}).json()
    p = m["placements"][0]
    assert p["auto"] is True and p["start_s"] == 0.0 and p["end_s"] == pytest.approx(m["duration"], abs=0.01)
    # a bed added without a position is automatic too
    m = client.post(f"{ep}/music", json={"asset_id": aid, "role": "bed"}).json()
    assert [q["auto"] for q in m["placements"] if q["role"] == "bed"] == [True, True]
    assert any(q.get("no_room") for q in m["placements"])   # the first one fills everything: no room left
