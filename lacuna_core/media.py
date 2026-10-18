"""Immutable source media references and a read-only, seekable sample pool.

Source audio is never modified. A `MediaRef` is identified by a content hash (`media_id`);
the path is only a locator and can be relinked without touching the EDL.
"""
from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import numpy as np
import soundfile as sf

_HASH_BLOCK = 1 << 20


def to_samples(seconds: float, sample_rate: int) -> int:
    """Seconds -> nearest integer sample index (all EDL arithmetic is in integer samples)."""
    return int(round(seconds * sample_rate))


def to_seconds(samples: int, sample_rate: int) -> float:
    return samples / sample_rate


def content_hash(path: str | Path) -> str:
    """Stable media id: sha256 of the file bytes (independent of file name / location)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(_HASH_BLOCK):
            h.update(block)
    return "sha256:" + h.hexdigest()


@dataclass(frozen=True)
class MediaRef:
    media_id: str
    path: str
    sample_rate: int
    channels: int
    frames: int

    @classmethod
    def probe(cls, path: str | Path, media_id: str | None = None) -> "MediaRef":
        info = sf.info(str(path))
        return cls(media_id or content_hash(path), str(path), info.samplerate,
                   info.channels, info.frames)

    def to_dict(self) -> dict:
        return dict(media_id=self.media_id, path=self.path, sample_rate=self.sample_rate,
                    channels=self.channels, frames=self.frames)

    @classmethod
    def from_dict(cls, d: dict) -> "MediaRef":
        return cls(**d)


@cache
def ffmpeg_has_soxr() -> bool:
    """Some ffmpeg builds (e.g. common static macOS builds) ship without libsoxr."""
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-buildconf"], capture_output=True, text=True)
    except FileNotFoundError:      # no ffmpeg at all: the decode that follows says so in words
        return False
    return "--enable-libsoxr" in out.stdout + out.stderr


def resample_filter(sample_rate: int) -> str:
    if ffmpeg_has_soxr():
        return f"aresample={sample_rate}:resampler=soxr"
    # swr with a long windowed-sinc filter: transparent for podcast speech/music
    return f"aresample={sample_rate}:resampler=swr:filter_size=64:phase_shift=10:cutoff=0.97"


def conform(src: str | Path, dst: str | Path, sample_rate: int, channels: int = 1) -> MediaRef:
    """Convert foreign media (e.g. a 48 kHz stereo music file) once to a project-rate WAV.

    The renderer requires all sources at the timeline rate; this is where sample-rate
    conversion happens (ffmpeg soxr, or high-quality swr where soxr is missing), so the hot render path stays sample-exact.
    """
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".tmp.wav")
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
           "-ac", str(channels), "-af", resample_filter(sample_rate),
           "-c:a", "pcm_f32le", str(tmp)]
    subprocess.run(cmd, check=True)
    tmp.replace(dst)
    return MediaRef.probe(dst)


class SourcePool:
    """Read-only access to registered media by id; reads are seeks, never whole-file loads.

    `repairs` (media id -> `declip.Repair`) restores clipped runs in what is read; the files
    themselves are never touched."""

    def __init__(self, media: dict[str, MediaRef], repairs: dict | None = None):
        self.media = dict(media)
        self.repairs: dict = {}
        self.set_repairs(repairs or {})
        self._handles: dict[str, sf.SoundFile] = {}

    def set_repairs(self, repairs: dict) -> None:
        """Swap the repairs in one step (a background scan may finish while the pool is in use;
        `repair_key` changes with them, so cached renders made without them are not reused)."""
        self.repairs = {k: r for k, r in repairs.items() if k in self.media}

    @property
    def repair_key(self) -> tuple:
        """What the repairs change, for render cache keys."""
        return tuple(sorted((k, len(r.starts), int(r.fixed.sum())) for k, r in self.repairs.items()))

    def _handle(self, media_id: str) -> sf.SoundFile:
        h = self._handles.get(media_id)
        if h is None:
            h = self._handles[media_id] = sf.SoundFile(self.media[media_id].path, "r")
        return h

    def read(self, media_id: str, start: int, stop: int) -> np.ndarray:
        """Mono float32 samples for [start, stop); zero-padded outside the file."""
        n = stop - start
        out = np.zeros(n, dtype=np.float32)
        frames = self.media[media_id].frames
        lo, hi = max(start, 0), min(stop, frames)
        if hi > lo:
            h = self._handle(media_id)
            h.seek(lo)
            x = h.read(hi - lo, dtype="float32", always_2d=True)
            out[lo - start:lo - start + len(x)] = x.mean(axis=1) if x.shape[1] > 1 else x[:, 0]
            r = self.repairs.get(media_id)
            if r is not None:
                out[lo - start:hi - start] = r.apply(out[lo - start:hi - start], lo)
        return out

    def close(self) -> None:
        for h in self._handles.values():
            h.close()
        self._handles.clear()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
