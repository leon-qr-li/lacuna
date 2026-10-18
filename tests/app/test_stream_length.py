"""Audio streams always send exactly the bytes their Content-Length promised (full-scan fix,
2026-10-18): the music page changes the mix while the old mix is still streaming, and the old
stream used to end short ("Too little data for declared Content-Length" in the console)."""
import shutil

import pytest

from lacuna_app.episode import Episode
from lacuna_app.library import Library
from lacuna_app.music import EpisodeMusic
from lacuna_app.store import Workspace

from .synth import EPISODE, make_workspace, write_music

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


@pytest.mark.parametrize("solo_s", [1.0, 6.0])        # the mix gets shorter / longer mid-stream
def test_mix_stream_keeps_its_length_when_the_music_changes_mid_stream(tmp_path, solo_s):
    ws = Workspace(make_workspace(tmp_path / "ws"))
    lib = Library(ws)
    a = lib.add_file(write_music(tmp_path / "in" / "j.wav", 8.0), "intro")
    m = EpisodeMusic(ws, Episode(ws, EPISODE), lib)
    pid = m.add(a["id"], "intro", solo_s=4.0)["id"]
    enabled = m.ep.enabled
    total = m.wav_size(enabled)
    for first, last in [(0, total - 1), (1000, total - 1), (40, 200_000)]:
        stream = m.iter_wav(enabled, first, last)
        got = len(next(stream)) + len(next(stream))
        m.update(pid, solo_s=solo_s)               # someone changes the intro on the page
        got += sum(len(c) for c in stream)
        assert got == last - first + 1
        m.update(pid, solo_s=4.0)
