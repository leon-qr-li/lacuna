"""Generate three short TEST music tracks into a LACUNA workspace's media library.

Leon wanted something to try the music feature (D45) with, without hunting for real music.
These are synthesised here (chords, bass, arpeggio, light drums), not real songs. File names
and BGM credits say so, so a test credit never ends up in real show notes by accident.

    python scripts/make_demo_music.py --workspace C:\\Projects\\LACUNA_Workspace

Safe to run again: output is deterministic, so the library keeps one entry per track.
"""
from __future__ import annotations

import argparse
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lacuna_app.library import FOLDERS, Library
from lacuna_app.store import Workspace

SR = 44100
CREDIT_ARTIST = "LACUNA 生成的测试音乐"

# name, kind, seconds, bpm, root midi note, chord progression (semitones from root), title, note
TRACKS = [
    ("测试音乐_片头.wav", "jingle", 25.0, 96, 57, [(0, 4, 7), (-3, 0, 4), (5, 9, 12), (7, 11, 14)],
     "测试片头", "生成的测试音乐（片头用），不是真歌"),
    ("测试音乐_间奏.wav", "music", 18.0, 84, 55, [(0, 3, 7), (5, 8, 12), (-2, 2, 5), (3, 7, 10)],
     "测试间奏", "生成的测试音乐（间奏用），不是真歌"),
    ("测试音乐_片尾.wav", "jingle", 45.0, 100, 60, [(0, 4, 7), (7, 11, 14), (-3, 0, 4), (5, 9, 12)],
     "测试片尾", "生成的测试音乐（片尾用），不是真歌"),
]


def hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def tone(f: float, n: int, harmonics: int = 6, decay: float = 0.0) -> np.ndarray:
    t = np.arange(n) / SR
    out = sum(np.sin(2 * np.pi * f * k * t) / k ** 1.4 for k in range(1, harmonics + 1))
    if decay:
        out = out * np.exp(-t * decay)
    return out


def adsr(n: int, a: float = 0.02, r: float = 0.1) -> np.ndarray:
    env = np.ones(n)
    na, nr = min(n, int(a * SR)), min(n, int(r * SR))
    env[:na] = np.linspace(0, 1, na)
    if nr:
        env[-nr:] *= np.linspace(1, 0, nr)
    return env


def render(seconds: float, bpm: int, root: int, prog: list[tuple[int, ...]], seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    left, right = np.zeros(n), np.zeros(n)
    beat = 60.0 / bpm
    bar = 4 * beat
    nb = int(bar * SR)

    def add(sig: np.ndarray, start: int, pan: float = 0.0) -> None:
        end = min(n, start + len(sig))
        if end <= start:
            return
        s = sig[: end - start]
        left[start:end] += s * (1 - pan) / 2 ** 0.5
        right[start:end] += s * (1 + pan) / 2 ** 0.5

    for b in range(int(np.ceil(seconds / bar))):
        chord = prog[b % len(prog)]
        s0 = int(b * bar * SR)
        # pad: slightly detuned chord tones, spread across the stereo field
        for i, iv in enumerate(chord):
            for det, pan in ((-0.06, -0.5), (0.06, 0.5)):
                add(0.07 * tone(hz(root + iv + det), nb, 4) * adsr(nb, 0.3, 0.4), s0, pan * (0.4 + 0.3 * i / 2))
        # bass on beats 1 and 3
        for k in (0, 2):
            nn = int(beat * 1.8 * SR)
            add(0.22 * tone(hz(root - 12 + chord[0]), nn, 3, decay=2.5) * adsr(nn, 0.01, 0.1), s0 + int(k * beat * SR))
        # arpeggio in eighth notes
        for k in range(8):
            iv = chord[k % len(chord)] + (12 if k >= 4 else 0)
            nn = int(beat / 2 * SR)
            add(0.06 * tone(hz(root + 12 + iv), nn, 3, decay=6) * adsr(nn, 0.005, 0.05), s0 + int(k * beat / 2 * SR),
                0.6 if k % 2 else -0.6)
        # drums: kick on 1/3, snare-ish noise on 2/4, hats on eighths
        for k in range(4):
            st = s0 + int(k * beat * SR)
            nk = int(0.25 * SR)
            t = np.arange(nk) / SR
            if k in (0, 2):
                add(0.5 * np.sin(2 * np.pi * (50 + 90 * np.exp(-t * 30)) * t) * np.exp(-t * 14), st)
            else:
                add(0.12 * rng.standard_normal(nk) * np.exp(-t * 22), st)
        for k in range(8):
            nh = int(0.05 * SR)
            add(0.03 * np.diff(rng.standard_normal(nh + 1)) * np.exp(-np.arange(nh) / SR * 80),
                s0 + int(k * beat / 2 * SR), 0.3)
    mix = np.stack([left, right], axis=1)
    fade = np.ones(n)
    fi, fo = int(1.0 * SR), int(3.0 * SR)
    fade[:fi] = np.linspace(0, 1, fi)
    fade[-fo:] = np.linspace(1, 0, fo)
    mix *= fade[:, None]
    return mix / np.max(np.abs(mix)) * 10 ** (-3 / 20)


def write_wav(path: Path, audio: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    tmp = path.with_name(path.name + ".part")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    tmp.replace(path)


def make(ws: Workspace) -> list[dict]:
    lib = Library(ws)
    lib.ensure_dirs()
    out = []
    for i, (name, kind, secs, bpm, root, prog, title, note) in enumerate(TRACKS):
        path = lib.dir / FOLDERS[kind] / name
        write_wav(path, render(secs, bpm, root, prog, seed=i))
        asset = lib.add_file(path, kind, note)
        asset = lib.update(asset["id"], credit={"title": title, "artist": CREDIT_ARTIST})
        out.append(asset)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workspace", required=True)
    args = ap.parse_args()
    for a in make(Workspace(args.workspace).ensure()):
        print(f"{a['file']}  {a['duration_s']:.1f}s  {a['lufs']:.1f} LUFS")


if __name__ == "__main__":
    main()
