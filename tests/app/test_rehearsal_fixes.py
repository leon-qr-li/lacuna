"""Fixes found by the end-to-end rehearsal of a long import (docs/status/rehearsal-e2e.md)."""
import shutil
import subprocess

import pytest
import soundfile as sf

from lacuna_app.episode import Episode
from lacuna_app.exporter import Exporter
from lacuna_app.first_cut import ClaudeFirstCut
from lacuna_app.importer import Importer
from lacuna_app.store import Workspace

from .fake_claude import FakeFirstCutAnthropic
from .synth import fake_asr, write_recordings

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


def _trim(src, dst, seconds):
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-i", str(src), "-t", str(seconds), str(dst)],
                   check=True)
    return dst


@pytest.mark.parametrize("short", ["Pei", "Leon"])
def test_longer_track_keeps_its_tail(tmp_path, short):
    """Tracks of different length: the episode runs to the end of the longer one (it used to be cut to
    the shorter track, silently dropping whatever the other host said after it ended)."""
    rec = write_recordings(tmp_path / "rec")
    rec[short] = _trim(rec[short], tmp_path / f"{short}_short.wav", 40)
    ws = Workspace(tmp_path / "ws").ensure()
    imp = Importer(ws, first_cut_factory=lambda: ClaudeFirstCut(client=FakeFirstCutAnthropic()), asr_backend=fake_asr)
    imp.start("EP_LEN", "长短不一", str(rec["Leon"]), str(rec["Pei"]), wait=True)
    job = imp.status("EP_LEN")
    assert job["state"] == "done", job["error"]
    assert job["result"]["raw_duration"] == pytest.approx(60.0, abs=0.01)

    ep = Episode(ws, "EP_LEN")
    s = ep.summary()
    ends = {t["name"]: t["clips"][-1][1] for t in s["tracks"]}
    long_host = "Leon" if short == "Pei" else "Pei"
    assert ends[long_host] > ends[short]
    ep.review_all("approve", None)
    ex = Exporter(ws)
    ex.start(ep, ["wav"], wait=True)
    st = ex.status("EP_LEN")
    assert st["state"] == "done", st["error"]
    wav = ex.dir_for("EP_LEN") / st["result"]["files"]["wav"]
    assert sf.info(str(wav)).duration == pytest.approx(ep.summary()["duration"], abs=0.05)
    assert ep.summary()["duration"] > 45       # past the 40 s end of the short track
