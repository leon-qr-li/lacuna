"""Shared helpers for the S2 ASR spike.

Every engine script writes one JSON file with the same schema so that
compare.py can treat them uniformly:

{
  "engine": str, "model": str, "audio": str, "config": {...},
  "audio_s": float, "wall_s": float, "rtf": float, "load_s": float,
  "peak_rss_mb": float,
  "segments": [ {"start": s, "end": s, "text": str, "event": str|None,
                 "tokens": [ {"t": str, "start": s, "end": s|None}, ... ] } ],
  "text": str   # concatenation of segment texts
}

Times are absolute seconds relative to the start of the excerpt file.
"""
from __future__ import annotations

import json
import os
import resource
import time
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 16000


def load_wav(path: str) -> np.ndarray:
    x, sr = sf.read(path, dtype="float32", always_2d=False)
    if x.ndim > 1:
        x = x.mean(axis=1)
    if sr != SR:
        raise SystemExit(f"{path}: expected {SR} Hz, got {sr}. Resample with ffmpeg first.")
    return x


def peak_rss_mb() -> float:
    # ru_maxrss is KiB on Linux, bytes on macOS
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / (1024 * 1024) if os.uname().sysname == "Darwin" else r / 1024


def silero_segments(audio: np.ndarray, vad_model: str, threshold: float = 0.5,
                    min_silence: float = 0.3, min_speech: float = 0.2,
                    max_speech: float = 20.0, pad: float = 0.2) -> list[tuple[float, float]]:
    """Speech segments via sherpa-onnx Silero VAD, padded and merged."""
    import sherpa_onnx as so

    cfg = so.VadModelConfig()
    cfg.silero_vad.model = vad_model
    cfg.silero_vad.threshold = threshold
    cfg.silero_vad.min_silence_duration = min_silence
    cfg.silero_vad.min_speech_duration = min_speech
    cfg.silero_vad.max_speech_duration = max_speech
    cfg.sample_rate = SR
    win = cfg.silero_vad.window_size
    vad = so.VoiceActivityDetector(cfg, buffer_size_in_seconds=600)
    segs = []
    i = 0
    while i < len(audio):
        vad.accept_waveform(audio[i:i + win])
        i += win
        while not vad.empty():
            s = vad.front
            segs.append((s.start / SR, (s.start + len(s.samples)) / SR))
            vad.pop()
    vad.flush()
    while not vad.empty():
        s = vad.front
        segs.append((s.start / SR, (s.start + len(s.samples)) / SR))
        vad.pop()
    dur = len(audio) / SR
    padded = []
    for a, b in segs:
        a, b = max(0.0, a - pad), min(dur, b + pad)
        if padded and a <= padded[-1][1]:
            padded[-1] = (padded[-1][0], b)
        else:
            padded.append((a, b))
    return padded


def fixed_chunks(dur: float, size: float = 30.0) -> list[tuple[float, float]]:
    out, t = [], 0.0
    while t < dur:
        out.append((t, min(dur, t + size)))
        t += size
    return out


class Timer:
    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *a):
        self.s = time.perf_counter() - self.t0


def write_result(path: str, engine: str, model: str, audio_path: str, audio_s: float,
                 load_s: float, wall_s: float, segments: list[dict], config: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    res = {
        "engine": engine, "model": model, "audio": os.path.basename(audio_path),
        "config": config, "audio_s": round(audio_s, 3), "load_s": round(load_s, 2),
        "wall_s": round(wall_s, 2), "rtf": round(wall_s / audio_s, 4),
        "peak_rss_mb": round(peak_rss_mb(), 1),
        "segments": segments,
        "text": "".join(s["text"] for s in segments),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(f"[{engine}] {os.path.basename(audio_path)} wall={wall_s:.1f}s rtf={res['rtf']:.3f} "
          f"peak_rss={res['peak_rss_mb']:.0f}MB chars={len(res['text'])} -> {path}")


def tokens_from_starts(toks: list[str], starts: list[float], seg_start: float,
                       seg_end: float, durations: list[float] | None = None) -> list[dict]:
    """Build token dicts. If no durations, end = next token start (capped at +0.6 s)."""
    out = []
    for i, (t, st) in enumerate(zip(toks, starts)):
        a = seg_start + float(st)
        if durations:
            b = a + float(durations[i])
        elif i + 1 < len(starts):
            b = min(seg_start + float(starts[i + 1]), a + 0.6)
        else:
            b = min(seg_end, a + 0.6)
        out.append({"t": t, "start": round(a, 3), "end": round(b, 3)})
    return out
