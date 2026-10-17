"""scripts/make_demo_music.py: generated test tracks land in the library, labelled as test music."""
import importlib.util
from pathlib import Path

import numpy as np

from lacuna_app.library import CONFIRMED, Library
from lacuna_app.store import Workspace

ROOT = Path(__file__).resolve().parents[2]


def load_script():
    spec = importlib.util.spec_from_file_location("make_demo_music", ROOT / "scripts/make_demo_music.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_demo_music_goes_into_library(tmp_path, monkeypatch):
    mod = load_script()
    # short versions keep the test fast; shape of the real tracks is unchanged
    monkeypatch.setattr(mod, "TRACKS", [t[:2] + (6.0,) + t[3:] for t in mod.TRACKS])
    ws = Workspace(tmp_path).ensure()
    assets = mod.make(ws)
    again = mod.make(ws)
    lib = Library(ws)
    assert [a["id"] for a in again] == [a["id"] for a in assets]
    assert len(lib.assets()) == 3
    assert [a["kind"] for a in lib.assets()] == ["intro", "interlude", "outro"]
    for a in lib.assets():
        assert "测试" in a["name"] and "测试" in a["note"]
        assert a["credit"]["status"] == CONFIRMED and "测试" in a["credit"]["artist"]
        assert abs(a["duration_s"] - 6.0) < 0.05
        assert -25 < a["lufs"] < -8


def test_demo_music_is_not_a_pure_tone():
    mod = load_script()
    audio = mod.render(4.0, 96, 57, mod.TRACKS[0][5], seed=0)
    assert audio.shape[1] == 2 and np.max(np.abs(audio)) <= 1.0
    spec = np.abs(np.fft.rfft(audio[:, 0]))
    strong = np.sum(spec > spec.max() * 0.1)
    assert strong > 50  # many partials (chords, bass, drums), not a sine
    assert not np.allclose(audio[:, 0], audio[:, 1])  # real stereo
