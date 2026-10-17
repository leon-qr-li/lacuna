"""Voice input with the real SenseVoice model on its shipped Mandarin clip.

Needs only the SenseVoice model folder under LACUNA_ASR_MODELS (see lacuna_app/asr.py);
skipped otherwise (CI does not download models).
"""
import os
from pathlib import Path

import pytest

from lacuna_app import asr
from lacuna_app.dictation import Dictation

MODELS = Path(os.environ.get("LACUNA_ASR_MODELS", "/nonexistent"))
pytestmark = pytest.mark.skipif(
    not (asr.sherpa_installed() and (MODELS / asr.SENSEVOICE / "model.int8.onnx").is_file()),
    reason="SenseVoice model not available (set LACUNA_ASR_MODELS)")


def test_dictation_real_sensevoice():
    """Punctuation/digits on (ITN), and faster than real time once the model is loaded."""
    wav = MODELS / asr.SENSEVOICE / "test_wavs" / "zh.wav"
    d = Dictation(MODELS)
    assert d.status()["dictation"]
    first = d.transcribe(wav.read_bytes())
    again = d.transcribe(wav.read_bytes())
    assert "开饭时间" in again["text"] and "9" in again["text"], again
    assert again["text"] == first["text"]
    assert again["seconds"] < again["audio_s"]
