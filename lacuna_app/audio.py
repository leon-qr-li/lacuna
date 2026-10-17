"""WAV encoding and byte-range helpers for streaming rendered audio."""
from __future__ import annotations

import io
import struct

import numpy as np

HEADER_BYTES = 44
SAMPLE_BYTES = 2  # PCM16


def wav_header(frames: int, sample_rate: int, channels: int = 1) -> bytes:
    data = frames * channels * SAMPLE_BYTES
    return b"".join([
        b"RIFF", struct.pack("<I", 36 + data), b"WAVE",
        b"fmt ", struct.pack("<IHHIIHH", 16, 1, channels, sample_rate,
                             sample_rate * channels * SAMPLE_BYTES, channels * SAMPLE_BYTES, 16),
        b"data", struct.pack("<I", data),
    ])


def pcm16(x: np.ndarray) -> bytes:
    y = np.clip(np.asarray(x, dtype=np.float32), -1.0, 1.0)
    return np.rint(y * 32767.0).astype("<i2").tobytes()


def wav_bytes(x: np.ndarray, sample_rate: int) -> bytes:
    x = np.asarray(x)
    ch = 1 if x.ndim == 1 else x.shape[1]
    frames = len(x)
    buf = io.BytesIO()
    buf.write(wav_header(frames, sample_rate, ch))
    buf.write(pcm16(x))
    return buf.getvalue()


def parse_range(header: str | None, total: int) -> tuple[int, int] | None:
    """Single `bytes=a-b` range -> inclusive (a, b) clamped to the file, or None for no/invalid."""
    if not header or not header.startswith("bytes=") or "," in header:
        return None
    a, _, b = header[6:].strip().partition("-")
    try:
        if a == "":                       # suffix range: last N bytes
            n = int(b)
            return (max(total - n, 0), total - 1) if n > 0 else None
        start = int(a)
        end = int(b) if b else total - 1
    except ValueError:
        return None
    if start >= total or end < start:
        return None
    return start, min(end, total - 1)
