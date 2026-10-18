"""Voice levels (backlog 7) and music levelled on what plays (backlog 20): lacuna_app/levels.py."""
import json
import shutil

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from lacuna_app import create_app, levels
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.episode import APPLIED, Episode, create_episode
from lacuna_app.learning import decisions
from lacuna_app.library import Library
from lacuna_app.music import BG_DB, EpisodeMusic
from lacuna_app.store import Workspace
from lacuna_core import MediaRef, Project, add_source_clip, new_timeline
from lacuna_core.master import LoudnessMeter

from .synth import EPISODE, SR, make_workspace, words_by_track, write_raw

EP = "EP_音量"


def uneven_workspace(root, pei_db=-12.0, clip_pei=False, pei_spikes=False):
    """The synthetic conversation with Pei recorded `pei_db` quieter (and optionally clipped)."""
    raw = root / "episodes" / EP / "raw"
    refs = write_raw(raw)
    for name in ("Leon", "Pei"):
        x, sr = sf.read(refs[name].path, dtype="float32")
        if name == "Pei":
            x = x * 10 ** (pei_db / 20)
            if clip_pei:                                   # a shout that hit the ceiling at 6 s and 14 s
                for t in (6.0, 14.0):
                    i = int(t * sr)
                    x[i:i + 400] = np.clip(x[i:i + 400] * 40, -1.0, 1.0)
        if name == "Pei" and pei_spikes:                   # short loud laughs: peaks far above her speech level
            for t in np.arange(1.0, 58.0, 4.0):
                i = int(t * sr)
                x[i:i + 100] += 0.6 * np.sin(np.arange(100) / 3.0)
        sf.write(refs[name].path, x, sr, subtype="FLOAT")
        refs[name] = MediaRef.probe(refs[name].path)
    tl = new_timeline(SR, ["Leon", "Pei"])
    for name, ref in refs.items():
        tl = add_source_clip(tl, name, ref)
    create_episode(Workspace(root), EP, {"title": "音量测试", "demo": False, "raw_offset_s": 0.0},
                   Project({r.media_id: r for r in refs.values()}, tl), [], {"tracks": words_by_track()})
    return Workspace(root)


def track_lufs(ep, name):
    """Loudness of one host as heard on the current timeline (rendered alone)."""
    from dataclasses import replace
    tl = ep.timeline_for(ep.enabled)
    solo = replace(tl, tracks=tuple(replace(t, mute=t.name != name) for t in tl.tracks))
    m = LoudnessMeter(ep.sr, 1, dual_mono=True, true_peak=False)
    with ep.lock:
        m.add(ep.previewer.render(solo, 0, solo.length).audio[:, 0])
    return m.integrated()


# ------------------------------------------------------------------ measuring + planning

def test_measure_and_auto_level_evens_the_hosts(tmp_path):
    ws = uneven_workspace(tmp_path, pei_db=-12.0)
    ep = Episode(ws, EP)
    m = levels.measurements(ep)
    assert m["Leon"]["lufs"] - m["Pei"]["lufs"] == pytest.approx(12.0, abs=0.6)
    assert (ep.dir / levels.FILE).is_file()
    gains = levels.auto_level(ep)
    assert gains["Pei"] - gains["Leon"] == pytest.approx(12.0, abs=0.6)
    assert abs(track_lufs(ep, "Leon") - track_lufs(ep, "Pei")) < 0.5
    assert abs(track_lufs(ep, "Pei") - levels.TARGET_LUFS) < 0.5
    v = levels.view(ep)
    assert v["even"] and all(abs(t["level_lufs"] - levels.TARGET_LUFS) < 0.2 for t in v["tracks"])
    # one undo step puts the raw levels back
    assert ep.undo().startswith("应用：")
    assert levels.current_gains(ep) == {"Leon": 0.0, "Pei": 0.0}
    assert not levels.view(ep)["even"]


def test_peaks_cap_the_gain_for_both_hosts(tmp_path):
    ws = uneven_workspace(tmp_path, pei_db=-12.0, pei_spikes=True)
    ep = Episode(ws, EP)
    m = levels.measurements(ep)
    g = levels.plan(m)
    out = {n: m[n]["lufs"] + g[n] for n in g}
    # Pei's laughs leave no room to reach the target: her loud peaks stop at the soft-clip knee ...
    assert m["Pei"]["loud_peak_db"] + g["Pei"] == pytest.approx(levels.PEAK_CEIL_DB, abs=0.1)
    assert out["Pei"] < levels.TARGET_LUFS - 1
    # ... and Leon comes down by the same amount, so the two stay even
    assert out["Leon"] == pytest.approx(out["Pei"], abs=0.15)
    # never more than MAX_SHORTFALL under the target
    big = {**m, "Pei": {**m["Pei"], "loud_peak_db": -1.0}}
    g2 = levels.plan(big)
    assert m["Pei"]["lufs"] + g2["Pei"] == pytest.approx(levels.TARGET_LUFS - levels.MAX_SHORTFALL, abs=0.1)


def test_clipping_is_detected_with_times_on_the_current_timeline(tmp_path):
    ws = uneven_workspace(tmp_path, pei_db=-6.0, clip_pei=True)
    ep = Episode(ws, EP)
    v = levels.view(ep)
    pei = next(t for t in v["tracks"] if t["name"] == "Pei")
    leon = next(t for t in v["tracks"] if t["name"] == "Leon")
    assert pei["clip_count"] == 2 and pei["clip_times"] == pytest.approx([6.0, 14.0], abs=0.02)
    assert leon["clip_count"] == 0 and leon["clip_times"] == []
    # cut 2 s before the second clip: it moves 2 s earlier; the first one is cut away
    ep.apply_op({"op": "cut", "start": int(5.5 * SR), "end": int(7.5 * SR), "tracks": None}, "删")
    pei = next(t for t in levels.view(ep)["tracks"] if t["name"] == "Pei")
    assert pei["clip_times"] == pytest.approx([12.0], abs=0.02)


def test_measurements_are_cached_until_the_source_changes(tmp_path, monkeypatch):
    ws = uneven_workspace(tmp_path)
    ep = Episode(ws, EP)
    levels.measurements(ep)
    calls = []
    monkeypatch.setattr(levels, "measure_track", lambda e, n: calls.append(n) or {"lufs": -20.0})
    levels.measurements(Episode(ws, EP))
    assert calls == []
    doc = json.loads((ep.dir / levels.FILE).read_text(encoding="utf-8"))
    doc["tracks"]["Pei"]["key"] = "stale"
    (ep.dir / levels.FILE).write_text(json.dumps(doc), encoding="utf-8")
    levels.measurements(Episode(ws, EP))
    assert calls == ["Pei"]


# ------------------------------------------------------------------ gains as edits

def test_one_gain_edit_per_track_and_undo_redo(tmp_path):
    ws = Workspace(make_workspace(tmp_path / "ws"))       # its first cut already has "Leon +3 dB" (e005)
    ep = Episode(ws, EPISODE)
    assert levels.current_gains(ep) == {"Leon": 3.0, "Pei": 0.0}
    levels.set_gains(ep, {"Leon": -2.0})
    levels.set_gains(ep, {"Leon": 1.5, "Pei": 4.0})
    assert levels.current_gains(ep) == {"Leon": 1.5, "Pei": 4.0}
    for t in ("Leon", "Pei"):
        applied = [e for e in ep.edits.values() if e.status == APPLIED and levels._gain_only(e, t)]
        assert len(applied) == 1
    assert levels.set_gains(ep, {"Leon": 1.5}) == {}               # no change, no undo step
    ep.undo()
    assert levels.current_gains(ep) == {"Leon": -2.0, "Pei": 0.0}
    ep.undo()
    assert levels.current_gains(ep) == {"Leon": 3.0, "Pei": 0.0}
    ep.redo()
    assert levels.current_gains(ep) == {"Leon": -2.0, "Pei": 0.0}
    assert levels.set_gains(ep, {"Leon": 99.0}) == {"Leon": levels.GAIN_MAX}
    with pytest.raises(KeyError):
        levels.set_gains(ep, {"♪music": 1.0})
    # survives a reload, and the render recipe carries the gain
    ep2 = Episode(ws, EPISODE)
    assert levels.current_gains(ep2)["Leon"] == levels.GAIN_MAX
    ops = [r["op"] for r in ep2.project_dict(ep2.enabled)["log"] if r["op"]["op"] == "track_gain"]
    assert [o["gain_db"] for o in ops if o["track"] == "Leon"] == [levels.GAIN_MAX]


def test_volume_edits_are_not_learned_as_editing_decisions(tmp_path):
    ws = Workspace(make_workspace(tmp_path / "ws"))
    ep = Episode(ws, EPISODE)
    edits = lambda: sorted(d.edit_id for d in decisions(ep) if d.category != "loudness")  # noqa: E731
    before = edits()
    levels.set_gains(ep, {"Pei": 3.0})
    levels.chat_volume(ep, "我的声音太低", 1.0)
    assert edits() == before
    assert not [d for d in decisions(ep) if d.source == "level"]


# ------------------------------------------------------------------ chat

@pytest.mark.parametrize("text,want", [
    ("我的声音太低了", {"tracks": ["Leon"], "delta_db": 2.0}),
    ("我声音有点小了", {"tracks": ["Leon"], "delta_db": 2.0}),
    ("Pei 的声音太大", {"tracks": ["Pei"], "delta_db": -2.0}),
    ("佩的音量调低 3 dB", {"tracks": ["Pei"], "delta_db": -3.0}),
    ("把裴的声音调高三个分贝", {"tracks": ["Pei"], "delta_db": 3.0}),
    ("我的音量稍微小一点", {"tracks": ["Leon"], "delta_db": -1.0}),
    ("两个人的声音都太小了", {"tracks": ["Leon", "Pei"], "delta_db": 2.0}),
    ("声音太低", {"tracks": ["Leon", "Pei"], "delta_db": 2.0}),
    ("Leon's volume is too low", {"tracks": ["Leon"], "delta_db": 2.0}),
    ("两人音量统一一下", {"even": True}),
    ("这句我的声音太低沉了，删掉", None),
    ("配乐的声音太大", None),
    ("背景音乐小一点", None),
    ("这段太长了", None),
    ("再短一点", None),
])
def test_parse_volume(text, want):
    assert levels.parse_volume(text, ["Leon", "Pei"], "Leon") == want


def api(ws):
    return TestClient(create_app(ws.root, MockEditorAdapter()))


def test_chat_route_changes_volume_without_the_ai(tmp_path):
    ws = uneven_workspace(tmp_path)
    c = api(ws)
    v0 = c.get(f"/api/episodes/{EP}").json()["version"]
    r = c.post(f"/api/episodes/{EP}/chat", json={"text": "Pei 的声音太小了，调高 4 dB", "playhead": 3.0}).json()
    assert r["adapter"] == "levels" and r["proposal"] is None and "4 dB" in r["reply"]
    s = c.get(f"/api/episodes/{EP}").json()
    assert s["version"] != v0 and s["can_undo"]
    assert {t["name"]: t["gain_db"] for t in s["tracks"]} == {"Leon": 0.0, "Pei": 4.0}
    r = c.post(f"/api/episodes/{EP}/chat", json={"text": "两个人音量统一一下", "playhead": 3.0}).json()
    assert r["adapter"] == "levels"
    lv = c.get(f"/api/episodes/{EP}/levels").json()
    assert lv["even"]
    # an editing instruction still goes to the editor
    r = c.post(f"/api/episodes/{EP}/chat", json={"text": "这段删掉", "playhead": 3.0}).json()
    assert r["adapter"] != "levels"
    log = json.loads((ws.episode_dir(EP) / "chat.json").read_text(encoding="utf-8"))["turns"]
    assert [t.get("volume", False) for t in log] == [True, True, False]


def test_levels_api(tmp_path):
    ws = uneven_workspace(tmp_path, pei_db=-10.0)
    c = api(ws)
    lv = c.get(f"/api/episodes/{EP}/levels").json()
    assert [t["name"] for t in lv["tracks"]] == ["Leon", "Pei"] and not lv["even"]
    assert lv["tracks"][1]["suggested_gain_db"] - lv["tracks"][0]["suggested_gain_db"] == pytest.approx(10.0, abs=0.6)
    r = c.post(f"/api/episodes/{EP}/levels/Pei", json={"delta_db": 1.5, "playhead": 10.0}).json()
    assert r["changed"] == {"Pei": 1.5} and r["playhead"] == 10.0 and r["levels"]["tracks"][1]["gain_db"] == 1.5
    r = c.post(f"/api/episodes/{EP}/levels/Pei", json={"gain_db": -3}).json()
    assert {t["name"]: t["gain_db"] for t in r["tracks"]}["Pei"] == -3.0
    assert c.post(f"/api/episodes/{EP}/levels/Pei", json={}).status_code == 422
    assert c.post(f"/api/episodes/{EP}/levels/Pei", json={"gain_db": 99}).status_code == 422
    assert c.post(f"/api/episodes/{EP}/levels/Nobody", json={"gain_db": 1}).status_code == 404
    r = c.post(f"/api/episodes/{EP}/levels/auto", json={}).json()
    assert r["levels"]["even"] and set(r["changed"]) == {"Leon", "Pei"}
    assert r["undo_label"]                                   # one step, labelled
    c.post(f"/api/episodes/{EP}/undo", json={})
    assert not c.get(f"/api/episodes/{EP}/levels").json()["even"]


# ------------------------------------------------------------------ import

@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_import_levels_the_new_episode(tmp_path):
    from lacuna_app.first_cut import ClaudeFirstCut
    from lacuna_app.importer import Importer
    from .fake_claude import FakeFirstCutAnthropic
    from .synth import fake_asr, write_recordings
    rec = write_recordings(tmp_path / "rec")
    x, sr = sf.read(rec["Pei"], dtype="float32")
    sf.write(rec["Pei"], x * 0.25, sr, subtype="PCM_16")             # Pei 12 dB quieter
    ws = Workspace(tmp_path / "ws").ensure()
    imp = Importer(ws, first_cut_factory=lambda: ClaudeFirstCut(client=FakeFirstCutAnthropic()), asr_backend=fake_asr)
    job = imp.start("EP009", "导入", str(rec["Leon"]), str(rec["Pei"]), wait=True)
    assert imp.status("EP009")["state"] == "done", job
    ep = Episode(ws, "EP009")
    g = levels.current_gains(ep)
    assert g["Pei"] - g["Leon"] == pytest.approx(12.0, abs=0.6)
    assert not ep.history["undo"]                           # part of the first state, nothing to undo
    assert levels.view(ep)["even"]
    doc = json.loads((ep.dir / levels.FILE).read_text(encoding="utf-8"))
    assert doc["auto"]["gains"] == g


def test_import_still_finishes_when_levelling_fails(tmp_path, monkeypatch):
    from lacuna_app.first_cut import ClaudeFirstCut
    from lacuna_app.importer import Importer
    from .fake_claude import FakeFirstCutAnthropic
    from .synth import fake_asr, write_recordings
    rec = write_recordings(tmp_path / "rec")
    ws = Workspace(tmp_path / "ws").ensure()
    monkeypatch.setattr(levels, "level_new_episode", lambda ep: 1 / 0)
    imp = Importer(ws, first_cut_factory=lambda: ClaudeFirstCut(client=FakeFirstCutAnthropic()), asr_backend=fake_asr)
    imp.start("EP010", "导入", str(rec["Leon"]), str(rec["Pei"]), wait=True)
    assert imp.status("EP010")["state"] == "done"
    assert levels.current_gains(Episode(ws, "EP010")) == {"Leon": 0.0, "Pei": 0.0}


# ------------------------------------------------------------------ music

def _two_part_song(path, sr=44100):
    """10 s quiet (-30 dBFS-ish) then 10 s loud chord: whole-file loudness is the loud half's."""
    t = np.arange(10 * sr) / sr
    quiet = 0.03 * np.sin(2 * np.pi * 440 * t)
    loud = 0.5 * np.sin(2 * np.pi * 440 * t)
    x = np.concatenate([quiet, loud]).astype(np.float32)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, np.stack([x, x], axis=1), sr)
    return path


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_music_is_levelled_on_the_part_that_plays(tmp_path):
    ws = Workspace(make_workspace(tmp_path / "ws"))
    lib = Library(ws)
    a = lib.add_file(_two_part_song(tmp_path / "in" / "score.wav"), "interlude")
    whole = levels.music_lufs(lib, a, 0.0, a["duration_s"])
    first = levels.music_lufs(lib, a, 0.0, 10.0)
    assert whole == pytest.approx(a["lufs"], abs=0.3)
    assert whole - first > 20                                   # the quiet half alone is far quieter
    ep = Episode(ws, EPISODE)
    m = EpisodeMusic(ws, ep, lib)
    m.add(a["id"], "bed", at_s=5.0, src_in_s=0.0, src_out_s=10.0)
    item = m.summary()["placements"][0]
    vl = m.voice_lufs(ep.enabled)
    # the quiet part is raised to sit LEVEL_LU from the voice, not left 20+ dB down
    assert item["level_db"] == pytest.approx(vl - 1.0 - first, abs=0.3)
    assert item["gain_db"] == 0.0
    # Leon's offset rides on top of the automatic level in the mix
    m.update(item["id"], gain_db=-4.0)
    tl, _, _ = m.mix()
    clip = next(c for t in tl.tracks if t.name.startswith("♪") for c in t.clips)
    assert clip.gain_db == pytest.approx(item["level_db"] - 4.0 - BG_DB, abs=0.05)   # a bed is background: BG_DB under


def test_music_level_falls_back_to_the_library_value(tmp_path):
    class BrokenLib:
        def media(self, *a):
            raise OSError("gone")
    assert levels.music_lufs(BrokenLib(), {"id": "x", "sha256": "s", "lufs": -14.0}, 0, 5) == -14.0
    assert levels.music_level_db(BrokenLib(), {"id": "y", "sha256": "s", "lufs": None}, {"src_out_s": 5}, -20, -1) == 0.0
