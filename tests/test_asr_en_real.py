"""Real sherpa-onnx English ASR (Parakeet-TDT + SenseVoice en) + features on the test clip shipped
with the Parakeet model.

Needs the English models (~650 MB, see lacuna_app/asr.py ENGINES["en"]): set LACUNA_ASR_MODELS to a
folder holding them (e.g. <workspace>/models after a first English import). Skipped otherwise.
"""
import os
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from lacuna_app import asr, features

MODELS = Path(os.environ.get("LACUNA_ASR_MODELS", "/nonexistent"))
pytestmark = pytest.mark.skipif(not (asr.sherpa_installed() and asr.models_present(MODELS, "en")),
                                reason="English sherpa-onnx models not available (set LACUNA_ASR_MODELS)")


def test_english_words_end_to_end():
    x, sr = sf.read(str(MODELS / asr.PARAKEET / "test_wavs" / "0.wav"), dtype="float32")
    assert sr == asr.SR
    x = np.concatenate([np.zeros(asr.SR // 2, np.float32), x, np.zeros(asr.SR // 2, np.float32)])
    x = x + 1e-4 * np.random.default_rng(0).standard_normal(len(x)).astype(np.float32)
    rec = asr.load_recognizers(MODELS, threads=2, lang="en")
    res = asr.transcribe(x, rec)
    words = [t for s in res["segments"] for t in s["par"]["tokens"]]
    assert len(words) > 5
    assert all("▁" not in t["t"] and " " not in t["t"] for t in words)          # whole words, merged
    assert all(t["end"] >= t["start"] for t in words)
    assert any(t["t"][0].isupper() for t in words)                              # Parakeet: cased
    sv = [t for s in res["segments"] for t in s["sv"]["tokens"]]
    assert sv and all("▁" not in t["t"] for t in sv)
    toks, _, doc = features.build({"A": res}, {"A": x}, "T", log=lambda *_: None, names={"A": "Ana"}, lang="en")
    flagged = sum(1 for t in toks["tracks"]["A"] if t["flag"])
    assert flagged <= len(words) // 3               # case / punctuation are not disagreements
    assert "The episode is in **English**" in doc
