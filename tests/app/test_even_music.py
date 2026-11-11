"""Background music evened out (docs/decisions/2026-10-30-even-background.md): a bed that suddenly gets loud is
turned down there, a long quiet stretch comes up a little, the talk-free full-level parts are left alone."""
import io
import shutil
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from lacuna_app import create_app
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.levels import EVEN_MAX_BOOST_DB, even_gains

from .synth import EPISODE, make_workspace
from .fake_claude import FakeCreditAnthropic as FakeAnthropic

EP = f"/api/episodes/{EPISODE}"


def song(sr=8000, seconds=30):
    t = np.arange(sr * seconds) / sr
    x = 0.1 * np.sin(2 * np.pi * 220 * t)
    x[sr * 10:sr * 12] *= 6          # suddenly 15.6 dB louder for 2 s
    x[sr * 20:sr * 26] *= 0.4        # 8 dB quieter for 6 s
    x[sr * 27:sr * 28] = 0           # a pause in the music
    return x.astype(np.float32)


def test_loud_bits_come_down_quiet_bits_up_pauses_stay():
    g = even_gains(song(), 8000)
    at = lambda s: next((d for a, b, d in g if a <= s < b), 0.0)       # noqa: E731
    assert at(11.0) <= -10                       # the burst comes down most of the way
    assert at(9.6) < 0                           # ... starting a little before it
    assert at(5.0) == 0 and at(16.0) == 0        # the song's normal level is left alone
    assert 0 < at(23.0) <= EVEN_MAX_BOOST_DB     # the quiet stretch comes up a little
    assert at(27.6) <= 1                         # silence is not raised
    assert even_gains(np.zeros(100, np.float32), 8000) == []


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_a_bed_with_a_loud_bit_is_evened_in_the_mix(tmp_path):
    ws = make_workspace(tmp_path / "ws")
    client = TestClient(create_app(ws, MockEditorAdapter(), web_dist=Path("/nonexistent"), credit_client=FakeAnthropic({})))
    f = tmp_path / "in" / "bumpy.wav"
    f.parent.mkdir(parents=True)
    sf.write(f, song(44100), 44100)
    r = client.post("/api/library/upload", params={"name": f.name, "kind": "bed", "note": ""}, content=f.read_bytes(),
                    headers={"Content-Type": "application/octet-stream"})
    aid = r.json()["asset"]["id"]
    m = client.post(f"{EP}/music", json={"asset_id": aid, "role": "bed", "at_s": 0.0}).json()
    assert m["placements"][0]["bg_db"] == 22.0
    # hear the music alone: mute the voice by comparing with and without the bed
    x, sr = sf.read(io.BytesIO(client.get(m["mix_url"]).content))
    client.delete(f"{EP}/music/{m['placements'][0]['id']}")
    v, _ = sf.read(io.BytesIO(client.get(client.get(f"{EP}/music").json()["mix_url"]).content))
    music = x[: len(v)] - v[: len(x)]
    db = lambda a, b: 10 * np.log10(np.mean(np.square(music[int(a * sr):int(b * sr)])))   # noqa: E731
    assert db(10.5, 11.5) - db(4, 8) < 5          # the burst was 15.6 dB over the rest
    assert db(4, 8) - db(21, 25) < 6              # the quiet stretch was 8 dB under
