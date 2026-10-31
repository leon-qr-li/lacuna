"""Media library + music placement / ducking (phase 6a, D45)."""
import json
import shutil

import numpy as np
import pytest

from lacuna_app.episode import Episode
from lacuna_app.library import CONFIRMED, NEED_NOTE, SUGGESTED, UNKNOWN, Library, credit_line, lookup_credit
from lacuna_app.music import (EpisodeMusic, bgm_credits, credits, final_duration, final_time, layout, speech_regions,
                               upgrade_v1)
from lacuna_app.store import Workspace

from .fake_claude import FakeCreditAnthropic as FakeAnthropic
from .synth import EPISODE, SR, make_workspace, write_music

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


@pytest.fixture
def ws(tmp_path):
    return Workspace(make_workspace(tmp_path / "ws"))


@pytest.fixture
def lib(ws):
    return Library(ws)


@pytest.fixture
def song(tmp_path):
    return write_music(tmp_path / "in" / "odyssey_theme.mp3", 12.0,
                       tags={"title": "The Sea", "artist": "Ludwig Göransson", "album": "The Odyssey (OST)",
                             "date": "2026"})


# ------------------------------------------------------------------ library

def test_add_copies_analyses_and_dedupes(lib, song):
    a = lib.add_file(song, "interlude", note="这是奥德赛的主题曲")
    assert a["id"].startswith("a_") and a["kind"] == "interlude"
    assert a["file"] == "music/odyssey_theme.mp3"
    assert (lib.dir / a["file"]).is_file() and song.is_file()          # copied; the original is untouched
    assert 11.9 < a["duration_s"] < 12.2
    assert a["channels"] == 2 and a["lufs"] is not None and -20 < a["lufs"] < 0
    # embedded tags give a first suggestion, never a confirmed credit
    assert a["credit"]["title"] == "The Sea" and a["credit"]["status"] == SUGGESTED and a["credit"]["year"] == 2026
    again = lib.add_file(song, "interlude")
    assert again["id"] == a["id"] and len(lib.assets()) == 1
    data = json.loads((lib.dir / "library.json").read_text("utf-8"))
    assert data["schema"] == 1 and data["assets"][0]["note"] == "这是奥德赛的主题曲"


def test_scan_picks_up_dropped_files_and_remove_keeps_file(lib, tmp_path):
    lib.ensure_dirs()
    write_music(lib.dir / "jingles" / "片头.wav", 5.0, stereo=False)
    (lib.dir / "jingles" / "readme.txt").write_text("x")
    new = lib.scan()
    assert [a["kind"] for a in new] == ["intro"] and new[0]["credit"]["status"] == UNKNOWN
    assert lib.scan() == []
    lib.remove(new[0]["id"])
    assert lib.assets() == [] and (lib.dir / "_removed" / "片头.wav").is_file()
    assert lib.scan() == []                              # removed files are not re-added


def test_old_kinds_are_migrated(lib, song):
    a = lib.add_file(song, "interlude")
    doc = json.loads((lib.dir / "library.json").read_text("utf-8"))
    doc["assets"][0]["kind"] = "jingle"                  # written by the first version (#23)
    (lib.dir / "library.json").write_text(json.dumps(doc), "utf-8")
    assert lib.asset(a["id"])["kind"] == "intro"
    assert lib.view()["kind_roles"]["trailer"] == "clip"
    assert lib.update(a["id"], kind="outro")["kind"] == "outro"
    with pytest.raises(ValueError):
        lib.update(a["id"], kind="jingle")


def test_rejects_non_audio(lib, tmp_path):
    p = tmp_path / "notes.txt"
    p.write_text("hi")
    with pytest.raises(ValueError):
        lib.add_file(p, "interlude")
    with pytest.raises(ValueError):
        lib.add_file(tmp_path / "missing.mp3", "interlude")


def test_credit_edit_confirm_and_line(lib, song):
    a = lib.add_file(song, "interlude")
    a = lib.update(a["id"], confirm=True)
    assert a["credit"]["status"] == CONFIRMED
    a = lib.update(a["id"], credit={"film": "奥德赛", "composer": "Ludwig Göransson", "year": "2026"})
    assert a["credit"]["source"] == "leon" and a["credit"]["year"] == 2026
    assert credit_line(a) == "《奥德赛》原声 · Ludwig Göransson — “The Sea”"
    assert credit_line({"name": "foo.mp3", "credit": {}}) == "foo"


def test_lookup_credit_stores_suggestion_with_sources(lib, song):
    a = lib.add_file(song, "interlude", note="这是奥德赛的主题曲")
    fake = FakeAnthropic({"title": "Odysseus", "artist": None, "composer": "Ludwig Göransson",
                          "album": "The Odyssey (Original Motion Picture Soundtrack)", "film": "奥德赛",
                          "year": 2026, "confidence": 0.8, "note": "官方原声第 1 首"}, pause_first=True)
    out = lookup_credit(lib, a["id"], client=fake)
    c = out["asset"]["credit"]
    assert c["title"] == "Odysseus" and c["status"] == SUGGESTED and c["source"] == "claude"
    assert c["sources"] == ["https://example.org/ost"] and out["message"] == "官方原声第 1 首"
    assert out["usage"]["cost_usd"] > 0
    # only text goes out: file name, tags, note, duration
    req = fake.calls[0]
    sent = json.loads(req["messages"][0]["content"])
    assert sent["leons_note"] == "这是奥德赛的主题曲" and sent["file_name"] == "odyssey_theme.mp3"
    assert any(t.get("type") == "web_search_20260209" for t in req["tools"])
    assert req["model"] == "claude-opus-5-5" and req["fallbacks"] == "default"
    assert len(fake.calls) == 2                       # the paused turn was continued


def test_lookup_without_note_skips_claude(lib, song):
    a = lib.add_file(song, "interlude", note="  ")
    fake = FakeAnthropic({"title": "X"})
    out = lookup_credit(lib, a["id"], client=fake)
    assert fake.calls == [] and out["usage"] is None and out["message"] == NEED_NOTE
    assert out["asset"]["credit"]["source"] != "claude"


def test_lookup_without_answer_changes_nothing(lib, song):
    a = lib.add_file(song, "interlude", note="某部电影的配乐")
    fake = FakeAnthropic({"title": None, "artist": None, "composer": None, "album": None, "film": None,
                          "year": None, "confidence": 0.1, "note": "查不到"})
    out = lookup_credit(lib, a["id"], client=fake)
    assert out["asset"]["credit"]["status"] == UNKNOWN and out["message"] == "查不到"


# ------------------------------------------------------------------ layout arithmetic

def test_layout_full_play_and_background_stretches():
    sr = 100
    assets = {"x": {"id": "x", "duration_s": 180.0}, "y": {"id": "y", "duration_s": 90.0}}
    ps = [{"id": "i", "asset_id": "x", "role": "intro", "solo_s": 10, "ramp_s": 2},
          {"id": "m", "asset_id": "y", "role": "interlude", "solo_s": 15, "ramp_s": 2, "at_base": 3000},
          {"id": "o", "asset_id": "x", "role": "outro", "src_out_s": 150, "bye_s": 120, "ramp_s": 2}]
    lay = layout(ps, assets, sr, voice_len=60000, to_voice=lambda b: b - 500)     # 5 s were cut before the point
    intro, mid, outro = lay.items
    # intro: the whole 3-minute song; alone for 10 s, then background under the talk to its end
    assert (intro.start, intro.length, intro.gap) == (0, 18000, 1000)
    assert intro.bg == [(1000, 18000)] and intro.ramp == 200
    # interlude at 25 s of the voice (+10 s of intro): rise 2 + full 15 + fall 2 s inserted, then background
    assert mid.gap_at == 2500 and mid.gap == 1900 and mid.anchor == mid.start == 3500
    assert mid.length == 9000 and mid.bg == [(5400, 12500)]
    assert lay.final(0) == 1000 and lay.final(2499) == 3499 and lay.final(2500) == 5400
    assert lay.voice(5400) == 2500 and lay.voice(4000) == 2500 and lay.voice(900) == 0
    # outro: trimmed at 2:30, the voice ends at its 2:00 -> it starts 2 min before the voice ends
    v_end = lay.final(60000)
    assert v_end == 62900 and outro.start == v_end - 12000 and outro.bg == [(outro.start, v_end)]
    assert outro.length == 15000 and lay.length == outro.end == v_end + 3000
    # played a few seconds under the talk before the gap
    lay2 = layout([dict(ps[1], pre_s=5)], assets, sr, 60000, lambda b: b)
    (m2,) = lay2.items
    assert m2.start == 3000 - 500 and m2.anchor == 3000 and m2.bg[0] == (2500, 3000) and m2.gap == 1900
    assert credits(lay2)[0]["start_s"] == 30.0          # show notes: the interlude is where the talk stops
    # fade in and fall back to background over different times
    (m3,) = layout([dict(ps[1], ramp_s=1, ramp_out_s=4)], assets, sr, 60000, lambda b: b).items
    assert m3.gap == 100 + 1500 + 400 and (m3.ramp, m3.ramp_out) == (100, 400) and m3.bg == [(3000 + 2000, 3000 + 9000)]
    # proposed / missing placements do not move anything
    lay3 = layout(ps + [{"id": "z", "asset_id": "gone", "role": "clip", "at_base": 10}], assets, sr, 6000, lambda b: b)
    assert [p["id"] for p in lay3.skipped] == ["z"]


def test_old_placements_play_whole_and_keep_their_timing():
    song = {"id": "x", "duration_s": 180.0}
    # cut at the automatic 30 s before: now the whole song; the voice still comes in at 26 s
    p = upgrade_v1({"role": "intro", "asset_id": "x", "src_in_s": 0.0, "src_out_s": 30.0, "overlap_s": 4.0}, song)
    assert p["src_out_s"] == 180.0 and p["solo_s"] == 26.0 and "overlap_s" not in p and p["bg_db"] == 20.0
    # trimmed by Leon: stays trimmed
    p = upgrade_v1({"role": "intro", "asset_id": "x", "src_in_s": 0.0, "src_out_s": 20.0, "overlap_s": 4.0}, song)
    assert p["src_out_s"] == 20.0 and p["solo_s"] == 16.0
    p = upgrade_v1({"role": "interlude", "asset_id": "x", "src_in_s": 0.0, "src_out_s": 20.0, "overlap_s": 2.0}, song)
    assert p["src_out_s"] == 180.0 and p["solo_s"] == 12.0         # the same 16 s gap
    p = upgrade_v1({"role": "outro", "asset_id": "x", "src_in_s": 0.0, "src_out_s": 60.0, "overlap_s": 4.0}, song)
    assert p["src_out_s"] == 180.0 and p["bye_s"] == 4.0
    assert upgrade_v1(dict(p), song) == p                              # already upgraded: unchanged


def test_speech_regions_bridge_short_pauses():
    sr = 1000
    x = np.zeros(5000)
    x[1000:2000] = 0.3
    x[2300:3000] = 0.3          # 0.3 s pause: bridged
    x[4000:4050] = 0.3          # 50 ms blip: dropped
    assert speech_regions(x, sr, -30.0, 100) == [(1100, 3100)]


# ------------------------------------------------------------------ the mix

@pytest.fixture
def ep(ws):
    e = Episode(ws, EPISODE)
    yield e
    e.close()


def _rms_db(x):
    return 20 * np.log10(np.sqrt(np.mean(np.asarray(x, dtype=np.float64) ** 2)) + 1e-12)


def test_intro_interlude_outro_mix_and_contract(ws, lib, ep, song, tmp_path):
    a = lib.add_file(song, "interlude")
    jingle = lib.add_file(write_music(tmp_path / "in" / "jingle.wav", 8.0, stereo=False), "intro")
    m = EpisodeMusic(ws, ep, lib)
    voice_len = ep.timeline_for(ep.enabled).length / SR
    assert bgm_credits(ws, EPISODE) == [] and final_time(ws, EPISODE, 10.0) == 10.0
    intro = m.add(jingle["id"], "intro", solo_s=3.0, ramp_s=1.0)
    assert intro["src_out_s"] == pytest.approx(8.0, abs=0.05)                  # the whole file by default
    mid = m.add(a["id"], "interlude", at_s=20.0, solo_s=2.0, ramp_s=1.0)        # 1 + 2 + 1 s inserted
    m.add(jingle["id"], "outro", bye_s=5.0)
    # voice now starts at 3 s, 4 s are inserted at 20 s; the outro starts 5 s before the voice ends
    assert final_time(ws, EPISODE, 0.0) == 3.0
    assert final_time(ws, EPISODE, 19.9) == pytest.approx(22.9, abs=0.01)
    assert final_time(ws, EPISODE, 20.0) == pytest.approx(27.0, abs=0.01)
    assert final_duration(ws, EPISODE) == pytest.approx(voice_len + 7.0 + 3.0, abs=0.02)
    cr = bgm_credits(ws, EPISODE)
    assert [c["role"] for c in cr] == ["intro", "interlude", "outro"]
    assert cr[1]["title"] == "The Sea" and cr[1]["credit_status"] == "suggested"
    assert cr[1]["start_s"] == pytest.approx(23.0, abs=0.01) and cr[0]["credit_line"] == "jingle"
    assert cr[1]["end_s"] - cr[1]["start_s"] == pytest.approx(12.0, abs=0.05)  # plays to the end, under the talk
    # the anchor moves with later voice edits: restoring the 4.2-5.3 s cut shifts it right by 1.1 s
    ep.review("e001", "restore")
    assert m.summary()["placements"][1]["voice_at_s"] == pytest.approx(21.1, abs=0.01)
    ep.review("e001", "apply")

    tl, media, lay = m.mix(channels=1)
    names = [t.name for t in tl.tracks]
    assert names[:2] == ["Leon", "Pei"] and len(names) == 5 and all(n.startswith("♪") for n in names[2:])
    stl, smedia, _ = m.mix(channels=2)
    assert len(stl.tracks) == 2 + 6 and {t.pan for t in stl.tracks[2:]} == {-1.0, 1.0}

    from lacuna_core import Renderer, RenderSettings, SourcePool
    with SourcePool(media) as pool:
        r = Renderer(pool, RenderSettings(channels=1))
        music_only = type(tl)(tl.sample_rate, tuple(t for t in tl.tracks if t.name.startswith("♪")))
        it = next(x for x in lay.items if x.p["id"] == mid["id"])
        track = next(t for t in music_only.tracks if mid["id"] in t.name)
        # one constant background stretch after the gap, 22 dB down (the default for new placements); no ducking that follows the speech
        assert [(d.start, d.end, d.depth_db) for d in track.ducks] == [(it.anchor + 4 * SR, it.end, 22.0)]
        full = r.render(music_only, it.anchor + int(1.2 * SR), it.anchor + int(2.8 * SR))
        under = r.render(music_only, it.anchor + 5 * SR, it.anchor + 7 * SR)
        assert 15 < _rms_db(full) - _rms_db(under) < 25
        # intro alone at the head: close to the voice loudness (within a few dB), not blasting
        voice = Renderer(pool, RenderSettings(channels=1)).render(tl, int(10 * SR), int(14 * SR))
        head = r.render(music_only, int(0.5 * SR), int(1.5 * SR))
        assert abs(_rms_db(head) - _rms_db(voice)) < 8
        # outro: background under the last words, full after them
        o = next(x for x in lay.items if x.p["role"] == "outro")
        assert o.bg == [(o.start, o.start + 5 * SR)]


def test_preview_series_rule_and_stream(ws, lib, ep, tmp_path):
    jingle = lib.add_file(write_music(tmp_path / "in" / "theme.wav", 10.0, stereo=False), "intro")
    m = EpisodeMusic(ws, ep, lib)
    p = m.add(jingle["id"], "intro", solo_s=4.0)
    wav, start = m.preview(p["id"])
    assert start == 0.0 and wav[:4] == b"RIFF" and len(wav) > SR * 2 * 10
    project = m.save_as_series("project")
    assert project["intro"]["asset_id"] == jingle["id"] and project["intro"]["solo_s"] == 4.0
    # a fresh episode (no music yet) is offered the project's opener; applying it places the intro
    other = EpisodeMusic(ws, ep, lib)
    other.remove(p["id"])
    sug = other.series_suggestion()
    assert sug and sug["from"] == "project" and sug["intro"] == "theme.wav"
    added = other.apply_series()
    assert [x["role"] for x in added] == ["intro"] and other.series_suggestion() is None
    # streamed mix: header + data in byte ranges
    total = other.wav_size(ep.enabled)
    body = b"".join(other.iter_wav(ep.enabled, 0, total - 1))
    assert len(body) == total and body[:4] == b"RIFF"
    assert total > (ep.timeline_for(ep.enabled).length + 4 * SR) * 2


def test_bed_and_clip(ws, lib, ep, tmp_path):
    bed = lib.add_file(write_music(tmp_path / "in" / "bed.wav", 30.0), "bed")
    clip = lib.add_file(write_music(tmp_path / "in" / "line.wav", 3.0, stereo=False), "dialogue")
    m = EpisodeMusic(ws, ep, lib)
    b = m.add(bed["id"], "bed", at_s=6.0, until_s=16.0)
    c = m.add(clip["id"], "clip", at_s=30.0, lead_s=0.5)
    lay = m.layout()
    ib, ic = (next(x for x in lay.items if x.p["id"] == k) for k in (b["id"], c["id"]))
    assert ib.gap == 0 and ib.length == pytest.approx(10 * SR, abs=2)
    assert ic.gap == 4 * SR and ic.start == lay.final(ic.gap_at) - 4 * SR + SR // 2
    tl, media, _ = m.mix()
    bed_track = next(t for t in tl.tracks if b["id"] in t.name)
    assert not bed_track.ducks and bed_track.clips[0].gain_db < -5          # simply lower, all the way
    assert bed_track.clips[0].fade_out == 3 * SR                               # cut at its end point: 3 s fade
    louder = m.update(b["id"], bg_db=10.0)
    assert louder["bg_db"] == 10.0
    tl2, _, _ = m.mix()
    assert next(t for t in tl2.tracks if b["id"] in t.name).clips[0].gain_db == pytest.approx(bed_track.clips[0].gain_db + 12, abs=0.01)   # 22 dB (bed default) -> 10
    with pytest.raises(ValueError):
        m.add(bed["id"], "interlude")        # an interlude needs a position (a bed without one is automatic)


def test_schema_1_file_and_series_rule_are_upgraded(ws, lib, ep, tmp_path):
    theme = lib.add_file(write_music(tmp_path / "in" / "theme.wav", 40.0, stereo=False), "intro")
    m = EpisodeMusic(ws, ep, lib)
    (ep.dir / "music.json").write_text(json.dumps({"schema": 1, "series": None, "series_dismissed": False, "draft": None,
        "placements": [{"id": "mu_old", "asset_id": theme["id"], "role": "intro", "at_base": None, "until_base": None,
                        "src_in_s": 0.0, "src_out_s": 30.0, "overlap_s": 4.0, "gain_db": 0.0, "lead_s": None,
                        "status": "applied", "source": "manual"}]}), "utf-8")
    (p,) = m.placements()
    assert p["src_out_s"] == 40.0 and p["solo_s"] == 26.0
    assert final_time(ws, EPISODE, 0.0) == 26.0                     # the voice comes in where it did
    m.update("mu_old", gain_db=-2.0)
    assert json.loads((ep.dir / "music.json").read_text("utf-8"))["schema"] == 2
    # a series rule saved before the full-play rule
    doc = json.loads((lib.dir / "library.json").read_text("utf-8"))
    doc.setdefault("series", []).append({"name": "旧", "default": True, "intro": {
        "asset_id": theme["id"], "src_in_s": 0.0, "src_out_s": 30.0, "overlap_s": 4.0, "gain_db": 0.0}, "outro": None})
    (lib.dir / "library.json").write_text(json.dumps(doc), "utf-8")
    (added,) = m.apply_series("旧")
    assert added["src_out_s"] == 40.0 and added["solo_s"] == 26.0
