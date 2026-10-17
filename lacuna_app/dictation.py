"""Voice input for the AI producer chat: a short mic recording → text, fully on this machine.

The browser records a clip (webm/opus in Chrome/Edge, mp4/aac in Safari) and posts the bytes;
ffmpeg decodes it to 16 kHz mono and the same SenseVoice model the episode import downloads
(``asr.SENSEVOICE``) turns it into text. ITN is on here (unlike the verbatim episode ASR) so the
chat gets punctuation and digits. Audio never leaves the machine; only the resulting text goes to
Claude, through the normal chat request, after Leon has read it.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable

import numpy as np

from . import asr

MAX_BYTES = 20 * 1024 * 1024          # ~10+ min of opus; the UI stops recording at 2 min
MAX_SECONDS = 180.0

Backend = Callable[[np.ndarray], str]  # 16 kHz mono float32 → text


class DictationError(Exception):
    """Something the user should read (Chinese)."""


class Dictation:
    def __init__(self, models_dir: Path, backend: Backend | None = None):
        self.models_dir = Path(models_dir)
        self._backend = backend
        self._lock = threading.Lock()

    def status(self) -> dict:
        if self._backend is not None:
            return {"dictation": True, "dictation_note": ""}
        if not asr.sherpa_installed():
            return {"dictation": False, "dictation_note": "没装识别引擎（pip install -e \".[asr]\"）"}
        if not (self.models_dir / asr.SENSEVOICE / "model.int8.onnx").is_file():
            return {"dictation": False, "dictation_note": "识别模型还没下载：导入一次新一集会自动下载"}
        return {"dictation": True, "dictation_note": ""}

    def _load(self) -> Backend:
        import sherpa_onnx as so

        m = self.models_dir / asr.SENSEVOICE
        rec = so.OfflineRecognizer.from_sense_voice(
            model=str(m / "model.int8.onnx"), tokens=str(m / "tokens.txt"),
            num_threads=max(1, min(4, (os.cpu_count() or 4) // 2)), language="zh", use_itn=True)

        def run(x: np.ndarray) -> str:
            st = rec.create_stream()
            st.accept_waveform(asr.SR, x)
            rec.decode_stream(st)
            return st.result.text

        return run

    def _ready(self) -> Backend:
        with self._lock:
            if self._backend is None:
                self._backend = self._load()
            return self._backend

    def warm(self) -> None:
        """Load the model in the background (called when recording starts: ~3 s the first time)."""
        if self._backend is None and self.status()["dictation"]:
            threading.Thread(target=self._ready, daemon=True).start()

    def transcribe(self, data: bytes) -> dict:
        if not data:
            raise DictationError("没有录到声音")
        if len(data) > MAX_BYTES:
            raise DictationError("录音太长了，分几次说吧")
        st = self.status()
        if not st["dictation"]:
            raise DictationError(st["dictation_note"])
        x = decode_bytes(data)
        dur = len(x) / asr.SR
        if dur > MAX_SECONDS:
            raise DictationError("录音太长了，分几次说吧")
        t0 = time.perf_counter()
        run = self._ready()
        with self._lock:                  # one recogniser, one clip at a time
            text = run(x) if dur >= 0.3 and np.abs(x).max(initial=0) > 1e-3 else ""
        return {"text": text.strip(), "audio_s": round(dur, 2), "seconds": round(time.perf_counter() - t0, 2)}


def decode_bytes(data: bytes) -> np.ndarray:
    """16 kHz mono float32 of an uploaded clip in any format ffmpeg reads."""
    # a temp file, not stdin: mp4 from Safari needs a seekable input
    fd, tmp = tempfile.mkstemp(prefix="lacuna-dictation-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        try:
            return asr.decode_16k(tmp)
        except subprocess.CalledProcessError:
            raise DictationError("这段录音解不开，再录一次试试")
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
