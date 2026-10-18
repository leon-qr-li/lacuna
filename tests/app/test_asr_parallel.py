"""asr.transcribe decodes each segment with Paraformer and SenseVoice at the same time; the output must
be exactly what decoding one after the other gives (real-model check: tests/test_asr_real.py)."""
import threading
import time
from types import SimpleNamespace

import numpy as np

from lacuna_app import asr


class FakeRecognizer:
    """Answers one token per segment; records which thread decoded and how many ran at once."""

    def __init__(self, name: str, busy: dict):
        self.name, self.busy, self.threads = name, busy, set()

    def create_stream(self):
        rec = self

        class Stream:
            def accept_waveform(self, sr, x):
                self.n = len(x)

            @property
            def result(self):
                return SimpleNamespace(text=f"{rec.name}{self.n}", tokens=[rec.name], timestamps=[0.1],
                                       event="<|Speech|>", emotion="<|NEUTRAL|>")
        return Stream()

    def decode_stream(self, st):
        self.threads.add(threading.current_thread().name)
        with self.busy["lock"]:
            self.busy["now"] += 1
            self.busy["max"] = max(self.busy["max"], self.busy["now"])
        time.sleep(0.02)
        with self.busy["lock"]:
            self.busy["now"] -= 1


def test_both_recognisers_run_together_and_output_is_unchanged(monkeypatch):
    segs = [(0.0, 1.0), (2.0, 2.5), (3.0, 4.25)]
    monkeypatch.setattr(asr, "vad_segments", lambda audio, model, progress=lambda f: None: segs)
    busy = {"lock": threading.Lock(), "now": 0, "max": 0}
    rec = asr.Recognizers(FakeRecognizer("P", busy), FakeRecognizer("S", busy), "vad")
    seen = []
    res = asr.transcribe(np.zeros(5 * asr.SR, np.float32), rec, lambda f, s: seen.append(f))
    want = [{"start": a, "end": b,
             "par": {"text": f"P{int(b * asr.SR) - int(a * asr.SR)}", "tokens": [{"t": "P", "start": round(a + 0.1, 3), "end": round(min(b, a + 0.7), 3)}]},
             "sv": {"text": f"S{int(b * asr.SR) - int(a * asr.SR)}", "event": "Speech", "emotion": "NEUTRAL",
                    "tokens": [{"t": "S", "start": round(a + 0.1, 3), "end": round(min(b, a + 0.7), 3)}]}}
            for a, b in segs]
    assert res == {"audio_s": 5.0, "segments": want}
    assert busy["max"] == 2                              # the two models decoded at the same time
    assert rec.paraformer.threads == {threading.current_thread().name}
    assert rec.sensevoice.threads and threading.current_thread().name not in rec.sensevoice.threads
    assert seen and max(seen) <= 1.0
