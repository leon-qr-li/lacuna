"""Clipping repair in the app (lacuna_app/declip.py, 验收 V7): episodes play, mix and export the
repaired audio, older episodes get it on open, and the recording itself is never written."""
import hashlib

import numpy as np
import pytest
import soundfile as sf

from lacuna_app import declip, levels
from lacuna_app.episode import Episode, create_episode
from lacuna_app.music import EpisodeMusic
from lacuna_app.store import Workspace
from lacuna_core import MediaRef, Project, SourcePool, add_source_clip, new_timeline

from .synth import SR, words_by_track, write_raw

EP = "EP_破音"


def clipped_workspace(root, drive=1.6):
    """The synthetic conversation with Pei recorded too hot: her peaks hit the 16-bit ceiling."""
    raw = root / "episodes" / EP / "raw"
    refs = write_raw(raw)
    x, sr = sf.read(refs["Pei"].path, dtype="float32")
    sf.write(refs["Pei"].path, np.clip(x / np.abs(x).max() * drive, -1.0, 1.0), sr, subtype="PCM_16")
    refs["Pei"] = MediaRef.probe(refs["Pei"].path)
    tl = new_timeline(SR, ["Leon", "Pei"])
    for name, ref in refs.items():
        tl = add_source_clip(tl, name, ref)
    create_episode(Workspace(root), EP, {"title": "破音测试", "demo": False, "raw_offset_s": 0.0},
                   Project({r.media_id: r for r in refs.values()}, tl), [], {"tracks": words_by_track()})
    return Workspace(root), refs


def sha(path) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def test_episode_plays_the_repaired_recording_and_never_writes_it(tmp_path):
    ws, refs = clipped_workspace(tmp_path)
    before = {n: sha(r.path) for n, r in refs.items()}
    ep = Episode(ws, EP)
    pei, leon = ep.media[refs["Pei"].media_id], ep.media[refs["Leon"].media_id]
    assert pei.patches is not None and len(pei.patches) > 0
    assert leon.patches is None                                    # Leon never clipped
    assert list((ep.dir / declip.DIR).glob("*.npz"))
    # review playback hears the repair: no flat tops left, never louder than the recording
    solo = ep.render(ep.enabled, 0, ep.timeline_for(ep.enabled).length)[:, 0]
    with SourcePool(ep.media, repaired=False) as raw:
        rec = raw.read(pei.media_id, 0, pei.frames)
    with SourcePool(ep.media) as pool:
        fixed = pool.read(pei.media_id, 0, pei.frames)
    assert not np.array_equal(fixed, rec)
    assert np.abs(fixed).max() <= np.abs(rec).max() + 1e-6
    flat = lambda y: int(np.count_nonzero(np.convolve(np.abs(y) >= 0.999, np.ones(3), "valid") == 3))  # noqa: E731
    assert flat(rec) > 20 and flat(fixed) == 0
    assert np.isfinite(solo).all()
    # saving the episode never saves the repair into the project, and the recording is untouched
    ep.save()
    assert "patches" not in (ep.dir / "state.json").read_text(encoding="utf-8")
    assert {n: sha(r.path) for n, r in refs.items()} == before


def test_the_volume_page_says_how_many_spots_were_repaired(tmp_path):
    ws, _ = clipped_workspace(tmp_path)
    v = levels.view(Episode(ws, EP))
    pei = next(t for t in v["tracks"] if t["name"] == "Pei")
    leon = next(t for t in v["tracks"] if t["name"] == "Leon")
    assert pei["clip_count"] > 0 and pei["clip_repaired"] == pei["clip_count"]
    assert pei["clip_kept"] == 0 and pei["clip_times"] == []
    assert (leon["clip_count"], leon["clip_repaired"], leon["clip_times"]) == (0, 0, [])


def test_older_episodes_are_repaired_when_opened_and_then_read_from_cache(tmp_path, monkeypatch):
    ws, refs = clipped_workspace(tmp_path)
    ep = Episode(ws, EP)
    first = ep.media[refs["Pei"].media_id].patches.digest()
    wipe(ws)
    calls = []
    real = declip.scan
    monkeypatch.setattr(declip, "scan", lambda *a, **k: calls.append(1) or real(*a, **k))
    again = Episode(ws, EP)
    assert len(calls) == 2                                         # both host sources, once
    assert again.media[refs["Pei"].media_id].patches.digest() == first
    Episode(ws, EP)
    assert len(calls) == 2                                         # cached from now on


def wipe(ws):
    """An episode imported before the repair existed: no declip folder."""
    d = ws.episode_dir(EP) / declip.DIR
    for f in d.iterdir():
        f.unlink()
    d.rmdir()


def test_a_failed_repair_never_stops_an_episode_from_opening(tmp_path, monkeypatch):
    ws, refs = clipped_workspace(tmp_path)
    wipe(ws)

    def boom(*a, **k):
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(declip, "scan", boom)
    ep = Episode(ws, EP)
    assert all(m.patches is None for m in ep.media.values())      # played as recorded
    assert ep.render(ep.enabled, 0, SR).shape == (SR, 1)
    assert levels.view(ep)["tracks"][1]["clip_count"] == 0


def test_the_music_mix_and_export_use_the_repaired_recording(tmp_path):
    ws, refs = clipped_workspace(tmp_path)
    ep = Episode(ws, EP)
    tl, media, _ = EpisodeMusic(ws, ep).mix(ep.enabled, 2)
    assert media[refs["Pei"].media_id].patches is ep.media[refs["Pei"].media_id].patches


def test_a_new_repair_version_rescans(tmp_path, monkeypatch):
    ws, refs = clipped_workspace(tmp_path)
    Episode(ws, EP)
    monkeypatch.setattr(declip, "VERSION", declip.VERSION + 1)
    calls = []
    real = declip.scan
    monkeypatch.setattr(declip, "scan", lambda *a, **k: calls.append(1) or real(*a, **k))
    Episode(ws, EP)
    assert len(calls) == 2


@pytest.mark.parametrize("drive", [4.0])
def test_long_shouts_are_listed_as_kept(tmp_path, drive):
    """Pinned at the ceiling far longer than a peak: left as recorded and listed on the page."""
    ws, _ = clipped_workspace(tmp_path, drive)
    pei = next(t for t in levels.view(Episode(ws, EP))["tracks"] if t["name"] == "Pei")
    assert pei["clip_count"] > 0 and pei["clip_kept"] > 0 and pei["clip_times"]
    assert pei["clip_repaired"] + pei["clip_kept"] <= pei["clip_count"]
