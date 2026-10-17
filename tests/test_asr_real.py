"""Real sherpa-onnx ASR + features on the Chinese test clips shipped with the Paraformer model.

Needs the models (~400 MB, see lacuna_app/asr.py): set LACUNA_ASR_MODELS to a folder holding
them (e.g. <workspace>/models after a first import). Skipped otherwise (CI does not download them).
"""
import os
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from lacuna_app import asr, features

MODELS = Path(os.environ.get("LACUNA_ASR_MODELS", "/nonexistent"))
pytestmark = pytest.mark.skipif(not (asr.sherpa_installed() and asr.models_present(MODELS)),
                                reason="sherpa-onnx models not available (set LACUNA_ASR_MODELS)")


def clip(name: str) -> np.ndarray:
    x, sr = sf.read(str(MODELS / asr.PARAFORMER / "test_wavs" / name), dtype="float32")
    assert sr == asr.SR
    return x


def test_two_track_conversation_end_to_end():
    a, b = clip("0.wav"), clip("1.wav")
    gap = np.zeros(int(0.8 * asr.SR), np.float32)
    leon = np.concatenate([a, gap, np.zeros_like(b), gap])
    pei = np.concatenate([np.zeros_like(a), gap, b, gap])
    rec = asr.load_recognizers(MODELS, threads=2)
    seen = []
    res = {tag: asr.transcribe(x + 1e-4 * np.random.default_rng(0).standard_normal(len(x)).astype(np.float32), rec,
                               lambda f, s: seen.append(f))
           for tag, x in (("L", leon), ("P", pei))}
    assert seen and max(seen) <= 1.0
    lt = "".join(s["par"]["text"] for s in res["L"]["segments"])
    pt = "".join(s["par"]["text"] for s in res["P"]["segments"])
    assert "研究" in lt and "全球" in pt           # 0.wav / 1.wav content
    for s in res["P"]["segments"]:
        assert s["start"] >= len(a) / asr.SR       # Pei's words are where Pei talks
    tokens, feats, doc = features.build(res, {"L": leon, "P": pei}, "EP_T", log=lambda *_: None)
    assert tokens["tracks"]["L"][0]["id"] == "L000000"
    assert all(t["end"] > t["start"] for tr in tokens["tracks"].values() for t in tr)
    assert feats["stats"]["floor_gaps_ge_1s"]["count"] == 0 or feats["floor_gaps"]
    assert "## 全文" in doc and "@0" in doc
