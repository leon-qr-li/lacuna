"""Two long raw host tracks of real Chinese speech, for an end-to-end rehearsal of an import.

    python scripts/rehearsal/make_long_episode.py <models-dir> <out-dir> [--minutes 120] [--sr 44100]

The speech is the sherpa-onnx test clips (shipped inside the ASR model folders), laid out as a
two-host conversation: alternating turns of 1-5 sentences, floor gaps from 0.1 to 4 s, a long
silence now and then, short backchannels on the other track and a little crosstalk. Leon's track
is ~6 dB quieter than Pei's and both carry a faint noise floor, like the EP001 Riverside tracks
(44.1 kHz s16 mono, aligned from t=0). Written in blocks, so a 2-hour pair needs little memory.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

CLIPS = {"Leon": ["paraformer/0.wav", "paraformer/2.wav", "paraformer/4-tianjin.wav", "paraformer/6-zh-en.wav"],
         "Pei": ["paraformer/1.wav", "paraformer/3-sichuan.wav", "paraformer/5-henan.wav", "sense-voice/zh.wav"]}
DIRS = {"paraformer": "sherpa-onnx-paraformer-zh-2023-09-14/test_wavs",
        "sense-voice": "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/test_wavs"}
GAIN = {"Leon": 0.5, "Pei": 1.0}


def load_clips(models: Path, sr: int) -> dict[str, list[np.ndarray]]:
    out = {}
    for host, names in CLIPS.items():
        out[host] = []
        for n in names:
            d, f = n.split("/")
            x, r = sf.read(str(models / DIRS[d] / f), dtype="float32", always_2d=True)
            x = x[:, 0]
            g = np.gcd(sr, r)
            y = resample_poly(x, sr // g, r // g).astype(np.float32)
            out[host].append(y / (np.abs(y).max() + 1e-9) * 0.5)
    return out


def layout(minutes: float, clips, sr: int, seed: int = 11) -> list[tuple[str, int, int, float]]:
    """[(host, start sample, clip index, gain)] for the whole conversation."""
    rng = np.random.default_rng(seed)
    total = int(minutes * 60 * sr)
    t, host, ev = int(1.0 * sr), "Leon", []
    while t < total - 10 * sr:
        for _ in range(int(rng.integers(1, 6))):                       # a turn of 1-5 sentences
            k = int(rng.integers(len(clips[host])))
            ev.append((host, t, k, GAIN[host]))
            t += len(clips[host][k]) + int(rng.uniform(0.15, 0.9) * sr)   # in-turn pauses
            if rng.random() < 0.08:                                     # the other one backchannels
                other = "Pei" if host == "Leon" else "Leon"
                ev.append((other, t - int(1.2 * sr), int(rng.integers(len(clips[other]))), GAIN[other] * 0.6))
        r = rng.random()
        gap = (rng.uniform(5, 12) if r < 0.02 else rng.uniform(1.5, 4.0) if r < 0.15
               else -rng.uniform(0.2, 1.0) if r < 0.22 else rng.uniform(0.1, 1.0))   # long / slow / crosstalk / normal
        t = max(t + int(gap * sr), 0)
        host = "Pei" if host == "Leon" else "Leon"
    return [e for e in ev if e[1] + 1 < total]


def write(out: Path, minutes: float, sr: int, models: Path) -> dict[str, Path]:
    clips = load_clips(models, sr)
    ev = layout(minutes, clips, sr)
    total = int(minutes * 60 * sr)
    out.mkdir(parents=True, exist_ok=True)
    paths = {}
    block = 60 * sr
    rng = np.random.default_rng(3)
    for host in ("Leon", "Pei"):
        mine = sorted((s, k, g) for h, s, k, g in ev if h == host)
        p = out / f"原始双轨_{host}.wav"
        with sf.SoundFile(str(p), "w", samplerate=sr, channels=1, subtype="PCM_16") as f:
            j = 0
            for b0 in range(0, total, block):
                b1 = min(b0 + block, total)
                x = (2e-4 * rng.standard_normal(b1 - b0)).astype(np.float32)
                while j < len(mine) and mine[j][0] + len(clips[host][mine[j][1]]) < b0:
                    j += 1
                for s, k, g in mine[j:]:
                    if s >= b1:
                        break
                    c = clips[host][k]
                    a, e = max(s, b0), min(s + len(c), b1)
                    if e > a:
                        x[a - b0:e - b0] += g * c[a - s:e - s]
                f.write(np.clip(x, -1, 1))
        paths[host] = p
    return paths


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("models", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--minutes", type=float, default=120.0)
    ap.add_argument("--sr", type=int, default=44100)
    a = ap.parse_args()
    for host, p in write(a.out, a.minutes, a.sr, a.models).items():
        print(host, p, round(sf.info(str(p)).duration / 60, 1), "min")


if __name__ == "__main__":
    main()
