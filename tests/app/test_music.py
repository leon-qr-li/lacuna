"""Media library + music placement / ducking (phase 6a, D43)."""
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

from lacuna_app.episode import Episode
from lacuna_app.library import CONFIRMED, SUGGESTED, UNKNOWN, Library, credit_line, lookup_credit
from lacuna_app.music import EpisodeMusic, bgm_credits, final_duration, final_time, layout, speech_regions
from lacuna_app.store import Workspace

from .synth import EPISODE, SR, make_workspace

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


def write_music(path: Path, seconds: float = 12.0, sr: int = 44100, stereo: bool = True, tags: dict | None = None,
                level: float = 0.3) -> Path:
    """A steady two-note chord (left 440 Hz, right 660 Hz); mp3 with tags when the suffix says so."""
    t = np.arange(int(seconds * sr)) / sr
    left = level * np.sin(2 * np.pi * 440 * t)
    right = level * np.sin(2 * np.pi * 660 * t)
    x = np.stack([left, right], axis=1) if stereo else ((left + right) / 2)[:, None]
    path.parent.mkdir(parents=True, exist_ok=True)
    wav = path.with_suffix(".src.wav") if path.suffix != ".wav" else path
    sf.write(str(wav), x.astype(np.float32), sr, subtype="PCM_16")
    if path.suffix != ".wav":
        meta = [a for k, v in (tags or {}).items() for a in ("-metadata", f"{k}={v}")]
        subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(wav), *meta,
                        "-codec:a", "libmp3lame", "-b:a", "192k", str(path)], check=True)
        wav.unlink()
    return path


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
    a = lib.add_file(song, "music", note="这是奥德赛的主题曲")
    assert a["id"].startswith("a_") and a["kind"] == "music"
    assert a["file"] == "music/odyssey_theme.mp3"
    assert (lib.dir / a["file"]).is_file() and song.is_file()          # copied; the original is untouched
    assert 11.9 < a["duration_s"] < 12.2
    assert a["channels"] == 2 and a["lufs"] is not None and -20 < a["lufs"] < 0
    # embedded tags give a first suggestion, never a confirmed credit
    assert a["credit"]["title"] == "The Sea" and a["credit"]["status"] == SUGGESTED and a["credit"]["year"] == 2026
    again = lib.add_file(song, "music")
    assert again["id"] == a["id"] and len(lib.assets()) == 1
    data = json.loads((lib.dir / "library.json").read_text("utf-8"))
    assert data["schema"] == 1 and data["assets"][0]["note"] == "这是奥德赛的主题曲"


def test_scan_picks_up_dropped_files_and_remove_keeps_file(lib, tmp_path):
    lib.ensure_dirs()
    write_music(lib.dir / "jingles" / "片头.wav", 5.0, stereo=False)
    (lib.dir / "jingles" / "readme.txt").write_text("x")
    new = lib.scan()
    assert [a["kind"] for a in new] == ["jingle"] and new[0]["credit"]["status"] == UNKNOWN
    assert lib.scan() == []
    lib.remove(new[0]["id"])
    assert lib.assets() == [] and (lib.dir / "_removed" / "片头.wav").is_file()
    assert lib.scan() == []                              # removed files are not re-added


def test_rejects_non_audio(lib, tmp_path):
    p = tmp_path / "notes.txt"
    p.write_text("hi")
    with pytest.raises(ValueError):
        lib.add_file(p, "music")
    with pytest.raises(ValueError):
        lib.add_file(tmp_path / "missing.mp3", "music")


def test_credit_edit_confirm_and_line(lib, song):
    a = lib.add_file(song, "music")
    a = lib.update(a["id"], confirm=True)
    assert a["credit"]["status"] == CONFIRMED
    a = lib.update(a["id"], credit={"film": "奥德赛", "composer": "Ludwig Göransson", "year": "2026"})
    assert a["credit"]["source"] == "leon" and a["credit"]["year"] == 2026
    assert credit_line(a) == "《奥德赛》原声 · Ludwig Göransson — “The Sea”"
    assert credit_line({"name": "foo.mp3", "credit": {}}) == "foo"


class FakeAnthropic:
    """Records the request; answers with a web search result block + a submit_credit tool call."""

    def __init__(self, answer, pause_first=False):
        self.answer, self.calls, self.pause_first = answer, [], pause_first
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.calls.append(kw)
        usage = SimpleNamespace(input_tokens=1000, output_tokens=200, cache_read_input_tokens=0,
                                cache_creation_input_tokens=0)
        if self.pause_first and len(self.calls) == 1:
            return SimpleNamespace(stop_reason="pause_turn", content=[], usage=usage, model="claude-opus-5-5")
        search = SimpleNamespace(type="web_search_tool_result",
                                 content=[SimpleNamespace(type="web_search_result", url="https://example.org/ost")])
        tool = SimpleNamespace(type="tool_use", name="submit_credit", input=self.answer)
        return SimpleNamespace(stop_reason="tool_use", content=[search, tool], usage=usage, model="claude-opus-5-5")


def test_lookup_credit_stores_suggestion_with_sources(lib, song):
    a = lib.add_file(song, "music", note="这是奥德赛的主题曲")
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
    assert len(fake.calls) == 2                       # the paused turn was continued


def test_lookup_without_answer_changes_nothing(lib, song):
    a = lib.add_file(song, "music")
    fake = FakeAnthropic({"title": None, "artist": None, "composer": None, "album": None, "film": None,
                          "year": None, "confidence": 0.1, "note": "查不到"})
    out = lookup_credit(lib, a["id"], client=fake)
    assert out["asset"]["credit"]["status"] == UNKNOWN and out["message"] == "查不到"


# ------------------------------------------------------------------ layout arithmetic

def test_layout_inserts_time_and_maps_both_ways():
    sr = 100
    assets = {"x": {"id": "x", "duration_s": 10.0}}
    ps = [{"id": "i", "asset_id": "x", "role": "intro", "src_in_s": 0, "src_out_s": 10, "overlap_s": 2},
          {"id": "m", "asset_id": "x", "role": "interlude", "src_in_s": 0, "src_out_s": 6, "overlap_s": 1,
           "at_base": 3000},
          {"id": "o", "asset_id": "x", "role": "outro", "src_in_s": 0, "src_out_s": 10, "overlap_s": 3}]
    lay = layout(ps, assets, sr, voice_len=6000, to_voice=lambda b: b - 500)      # 5 s were cut before the point
    intro, mid, outro = lay.items
    assert (intro.start, intro.length, intro.gap) == (0, 1000, 800)                 # voice enters at 8 s
    assert mid.gap_at == 2500 and mid.gap == 400 and mid.start == 2500 + 800 - 100
    assert lay.final(0) == 800 and lay.final(2499) == 3299 and lay.final(2500) == 3700
    assert outro.start == 6000 + 1200 - 300 and lay.length == outro.end == 7900
    assert lay.voice(3700) == 2500 and lay.voice(3500) == 2500 and lay.voice(100) == 0 and lay.voice(900) == 100
    # proposed / missing placements do not move anything
    lay2 = layout(ps + [{"id": "z", "asset_id": "gone", "role": "clip", "at_base": 10}], assets, sr, 6000, lambda b: b)
    assert [p["id"] for p in lay2.skipped] == ["z"]


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
    a = lib.add_file(song, "music")
    jingle = lib.add_file(write_music(tmp_path / "in" / "jingle.wav", 8.0, stereo=False), "jingle")
    m = EpisodeMusic(ws, ep, lib)
    voice_len = ep.timeline_for(ep.enabled).length / SR
    assert bgm_credits(ws, EPISODE) == [] and final_time(ws, EPISODE, 10.0) == 10.0
    m.add(jingle["id"], "intro", src_out_s=8.0, overlap_s=3.0)
    mid = m.add(a["id"], "interlude", at_s=20.0, src_out_s=6.0)               # default overlap 2 s
    m.add(jingle["id"], "outro", overlap_s=2.0)
    # voice now starts at 5 s, 2 s are inserted at 20 s
    assert final_time(ws, EPISODE, 0.0) == 5.0
    assert final_time(ws, EPISODE, 19.9) == pytest.approx(24.9, abs=0.01)
    assert final_time(ws, EPISODE, 20.0) == pytest.approx(27.0, abs=0.01)
    assert final_duration(ws, EPISODE) == pytest.approx(voice_len + 7.0 + 8.0 - 2.0, abs=0.01)
    cr = bgm_credits(ws, EPISODE)
    assert [c["role"] for c in cr] == ["intro", "interlude", "outro"]
    assert cr[1]["title"] == "The Sea" and cr[1]["credit_status"] == "suggested"
    assert cr[1]["start_s"] == pytest.approx(23.0, abs=0.01) and cr[0]["credit_line"] == "jingle"
    # the anchor moves with later voice edits: restoring the 4.2-5.3 s cut shifts it right by 1.1 s
    ep.review("e001", "restore")
    assert m.summary()["placements"][1]["voice_at_s"] == pytest.approx(21.1, abs=0.01)
    ep.review("e001", "apply")

    tl, media, lay = m.mix(channels=1)
    names = [t.name for t in tl.tracks]
    assert names[:2] == ["Leon", "Pei"] and len(names) == 5 and all(n.startswith("♪") for n in names[2:])
    stl, smedia, _ = m.mix(channels=2)
    assert len(stl.tracks) == 2 + 6 and {t.pan for t in stl.tracks[2:]} == {-1.0, 1.0}

    # loudness relation: the interlude in its gap plays near voice level; ducked under speech it is far lower
    from lacuna_core import Renderer, RenderSettings, SourcePool
    with SourcePool(media) as pool:
        r = Renderer(pool, RenderSettings(channels=1))
        music_only = type(tl)(tl.sample_rate, tuple(t for t in tl.tracks if t.name.startswith("♪")))
        it = next(x for x in lay.items if x.p["id"] == mid["id"])
        gap_mid = it.start + it.length // 2
        full = r.render(music_only, gap_mid - SR // 2, gap_mid + SR // 2)
        ducks = next(t for t in music_only.tracks if mid["id"] in t.name).ducks
        assert ducks, "music under speech must be ducked"
        d = ducks[0]
        under = r.render(music_only, d.start + d.ramp, min(d.end, d.start + d.ramp + SR // 4))
        assert _rms_db(full) - _rms_db(under) > 12
        # intro alone at the head: close to the voice loudness (within a few dB), not blasting
        voice = Renderer(pool, RenderSettings(channels=1)).render(tl, int(10 * SR), int(14 * SR))
        head = r.render(music_only, int(0.5 * SR), int(2.5 * SR))
        assert abs(_rms_db(head) - _rms_db(voice)) < 8


def test_preview_series_rule_and_stream(ws, lib, ep, tmp_path):
    jingle = lib.add_file(write_music(tmp_path / "in" / "theme.wav", 10.0, stereo=False), "jingle")
    m = EpisodeMusic(ws, ep, lib)
    p = m.add(jingle["id"], "intro", src_out_s=10.0)
    wav, start = m.preview(p["id"])
    assert start == 0.0 and wav[:4] == b"RIFF" and len(wav) > SR * 2 * 10
    rule = m.save_as_series("洛城二三事")
    assert rule["intro"]["asset_id"] == jingle["id"] and rule["default"]
    # a fresh episode (no music yet) is offered the series rule; applying it places the intro
    other = EpisodeMusic(ws, ep, lib)
    other.remove(p["id"])
    sug = other.series_suggestion()
    assert sug and sug["name"] == "洛城二三事"
    added = other.apply_series()
    assert [x["role"] for x in added] == ["intro"] and other.series_suggestion() is None
    # streamed mix: header + data in byte ranges
    total = other.wav_size(ep.enabled)
    body = b"".join(other.iter_wav(ep.enabled, 0, total - 1))
    assert len(body) == total and body[:4] == b"RIFF"
    assert total > (ep.timeline_for(ep.enabled).length + 6 * SR) * 2


def test_bed_and_clip(ws, lib, ep, tmp_path):
    bed = lib.add_file(write_music(tmp_path / "in" / "bed.wav", 30.0), "music")
    clip = lib.add_file(write_music(tmp_path / "in" / "line.wav", 3.0, stereo=False), "clip")
    m = EpisodeMusic(ws, ep, lib)
    b = m.add(bed["id"], "bed", at_s=6.0, until_s=16.0)
    c = m.add(clip["id"], "clip", at_s=30.0, lead_s=0.5)
    lay = m.layout()
    ib, ic = (next(x for x in lay.items if x.p["id"] == k) for k in (b["id"], c["id"]))
    assert ib.gap == 0 and ib.length == pytest.approx(10 * SR, abs=2)
    assert ic.gap == 4 * SR and ic.start == lay.final(ic.gap_at) - 4 * SR + SR // 2
    tl, media, _ = m.mix()
    bed_track = next(t for t in tl.tracks if b["id"] in t.name)
    assert bed_track.ducks and bed_track.clips[0].gain_db < -5
    with pytest.raises(ValueError):
        m.add(bed["id"], "bed")              # a bed needs a position
