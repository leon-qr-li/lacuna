"""Voice input for the chat: upload a recorded clip, get text back, all on this machine.

The recogniser is faked (the real SenseVoice path is in tests/test_asr_real.py when the models
are on disk); the upload, the ffmpeg decode of browser formats and the error messages are real.
"""
import io
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from lacuna_app import create_app
from lacuna_app.dictation import Dictation
from lacuna_app.editor import MockEditorAdapter

from .synth import make_workspace

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


def tone(seconds=1.5, sr=48000, amp=0.3) -> np.ndarray:
    t = np.arange(int(seconds * sr)) / sr
    return (amp * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def wav_bytes(x, sr=48000) -> bytes:
    b = io.BytesIO()
    sf.write(b, x, sr, format="WAV")
    return b.getvalue()


class Heard:
    def __init__(self, text="这句删掉"):
        self.text, self.calls = text, []

    def __call__(self, x):
        self.calls.append(x)
        return self.text


@pytest.fixture
def ws(tmp_path):
    return make_workspace(tmp_path / "ws")


def client(ws, dictation):
    return TestClient(create_app(ws, MockEditorAdapter(), web_dist=Path("/nonexistent"), dictation=dictation))


def test_clip_to_text_resampled_to_16k(ws):
    heard = Heard()
    c = client(ws, Dictation(ws / "models", backend=heard))
    assert c.get("/api/health").json()["dictation"] is True
    r = c.post("/api/dictation", content=wav_bytes(tone()), headers={"Content-Type": "audio/wav"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["text"] == "这句删掉" and abs(out["audio_s"] - 1.5) < 0.05
    (x,) = heard.calls
    assert x.dtype == np.float32 and abs(len(x) - 24000) < 400       # 48 kHz in, 16 kHz mono to the model


@pytest.mark.skipif(subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True)
                    .stdout.find("libopus") < 0, reason="ffmpeg without libopus")
def test_browser_webm_opus_decodes(ws, tmp_path):
    """Chrome/Edge MediaRecorder sends webm/opus; Safari sends mp4/aac. Both go through ffmpeg."""
    src = tmp_path / "a.wav"
    src.write_bytes(wav_bytes(tone()))
    webm = tmp_path / "a.webm"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(src), "-c:a", "libopus", str(webm)], check=True)
    heard = Heard("停顿短一点")
    r = client(ws, Dictation(ws / "models", backend=heard)).post(
        "/api/dictation", content=webm.read_bytes(), headers={"Content-Type": "audio/webm;codecs=opus"})
    assert r.status_code == 200 and r.json()["text"] == "停顿短一点"


def test_silence_and_bad_input(ws):
    heard = Heard()
    c = client(ws, Dictation(ws / "models", backend=heard))
    r = c.post("/api/dictation", content=wav_bytes(np.zeros(48000, np.float32)))
    assert r.status_code == 200 and r.json()["text"] == ""            # silence: nothing sent to the model
    assert heard.calls == []
    r = c.post("/api/dictation", content=b"")
    assert r.status_code == 422 and "没有录到" in r.json()["detail"]
    r = c.post("/api/dictation", content=b"not audio at all" * 10)
    assert r.status_code == 422 and "解不开" in r.json()["detail"]


def test_without_models_says_why(ws, monkeypatch):
    from lacuna_app import asr
    monkeypatch.setattr(asr, "sherpa_installed", lambda: True)
    d = Dictation(ws / "models")
    c = client(ws, d)
    h = c.get("/api/health").json()
    assert h["dictation"] is False and "模型" in h["dictation_note"]
    r = c.post("/api/dictation", content=wav_bytes(tone()))
    assert r.status_code == 422 and "模型" in r.json()["detail"]
    assert c.post("/api/dictation/warm").json() == {"ok": True}      # no-op, no crash
    monkeypatch.setattr(asr, "sherpa_installed", lambda: False)
    assert "识别引擎" in d.status()["dictation_note"]
