"""Automatic clipping repair in the app (lacuna_app/declip.py): review playback, the music mix and
export all hear the repaired hosts; the recordings are never written; the scan runs once."""
import hashlib
import threading

import numpy as np
import pytest
import soundfile as sf

from lacuna_app import declip, exporter
from lacuna_app.episode import Episode
from lacuna_app.music import EpisodeMusic
from lacuna_core import declip as core

from .synth import SR
from .test_levels import EP, uneven_workspace


def settle():
    """Wait for background scans (playback starts them) and forget what they found."""
    for t in threading.enumerate():
        if t.name.startswith("declip-"):
            t.join()


@pytest.fixture
def ws(tmp_path):
    settle()
    declip._mem.clear()
    yield uneven_workspace(tmp_path, pei_db=-6.0, clip_pei=True)
    settle()
    declip._mem.clear()


def digest(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def pei_ref(ep):
    return next(m for m in ep.media.values() if m.path.endswith("Pei.wav"))


def test_playback_starts_before_the_first_scan_and_picks_it_up(ws, monkeypatch):
    gate = threading.Event()
    real = declip.scan
    monkeypatch.setattr(declip, "scan", lambda *a: gate.wait(10) and real(*a))
    ep = Episode(ws, EP)
    a, b = int(5.9 * SR), int(6.1 * SR)
    pei = pei_ref(ep)
    before = ep.render(ep.enabled, a, b)                     # renders at once: nothing to apply yet
    assert ep.previewer.renderer.pool.repairs == {}
    gate.set()
    settle()
    assert pei.media_id in ep.previewer.renderer.pool.repairs
    after = ep.render(ep.enabled, a, b)                      # not the cached block from before
    assert not np.array_equal(before, after)


def test_playback_hears_the_repaired_recording_and_the_file_stays(ws):
    ep = Episode(ws, EP)
    pei = pei_ref(ep)
    before = digest(pei.path)
    raw = sf.read(pei.path, dtype="float32")[0]
    a, b = int(5.9 * SR), int(6.1 * SR)
    with ep.lock:
        r = declip.repair_for(ep, pei.media_id)
    assert r.fixed.any() and (~r.fixed).any()
    got = ep.previewer.renderer.pool.read(pei.media_id, a, b)
    assert not np.array_equal(got, raw[a:b]) and np.abs(got).max() > 1.0
    assert np.array_equal(got, r.apply(raw[a:b], a))
    # the long, far-over spot at 14 s plays as recorded
    c, d = int(13.95 * SR), int(14.1 * SR)
    assert np.array_equal(ep.previewer.renderer.pool.read(pei.media_id, c, d), raw[c:d])
    ep.render(ep.enabled, 0, ep.timeline_for(ep.enabled).length)
    assert digest(pei.path) == before
    assert list((ep.dir / declip.DIR).glob("*.npz"))


def test_the_scan_runs_once_then_comes_from_the_cache_file(ws, monkeypatch):
    ep = Episode(ws, EP)
    first = declip.repairs(ep)
    assert set(first) == {pei_ref(ep).media_id}        # Leon never clips: nothing to apply
    declip._mem.clear()
    monkeypatch.setattr(declip, "scan", lambda *a: (_ for _ in ()).throw(AssertionError("scanned again")))
    again = declip.repairs(Episode(ws, EP))
    mid = pei_ref(ep).media_id
    assert np.array_equal(again[mid].starts, first[mid].starts)


def test_an_unreadable_scan_plays_the_recording_as_it_is(ws, monkeypatch):
    def boom(*a):
        raise RuntimeError("bad file")
    monkeypatch.setattr(declip, "scan", boom)
    ep = Episode(ws, EP)
    assert declip.repairs(ep) == {}
    assert ep.render(ep.enabled, 0, SR).shape == (SR, 1)


def test_music_mix_and_export_use_the_repairs(ws, monkeypatch):
    ep = Episode(ws, EP)
    mid = pei_ref(ep).media_id
    pv_pool = EpisodeMusic(ws, ep)._player(ep.enabled)[1].renderer.pool
    settle()                                 # playback never waits for the first scan ...
    assert mid in pv_pool.repairs            # ... the repairs join the playing pool when it is done
    seen = []
    real = exporter.timeline_source

    def spy(pool, tl, channels):
        seen.append(dict(pool.repairs))
        return real(pool, tl, channels)
    monkeypatch.setattr(exporter, "timeline_source", spy)
    ex = exporter.Exporter(ws)
    ex.start(ep, ["wav"], channels=1, wait=True)
    assert ex.jobs[EP]["state"] == "done", ex.jobs[EP]["error"]
    assert seen and mid in seen[0]


def test_version_is_part_of_the_cache_name(ws):
    ep = Episode(ws, EP)
    declip.repairs(ep)
    assert all(p.name.startswith(f"v{core.VERSION}_") for p in (ep.dir / declip.DIR).iterdir())
