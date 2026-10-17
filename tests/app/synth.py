"""Small synthetic two-host workspace for backend tests and Playwright E2E.

Run directly to (re)create one: `python tests/app/synth.py <workspace-dir>`.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lacuna_core import MediaRef, Project, add_source_clip, new_timeline  # noqa: E402
from lacuna_app.episode import Edit, create_episode  # noqa: E402
from lacuna_app.store import Workspace  # noqa: E402

SR = 16000
DUR = 60.0
EPISODE = "EP_TEST_合成"
# (track, start, end) seconds of "speech"
TURNS = [("Leon", 0.5, 4.0), ("Pei", 5.5, 8.0), ("Leon", 9.2, 13.0), ("Pei", 11.0, 11.4),
         ("Pei", 13.4, 16.0), ("Leon", 18.0, 22.0), ("Pei", 22.3, 25.0), ("Leon", 26.5, 30.0),
         ("Pei", 31.0, 35.0), ("Leon", 36.5, 40.0), ("Pei", 40.3, 44.0), ("Leon", 46.0, 50.0),
         ("Pei", 50.5, 54.0), ("Leon", 55.0, 58.0)]
CHARS = "我们今天聊一部电影真的很好看对吧然后那个结尾"


def _speech(n: int, f0: float, rng) -> np.ndarray:
    t = np.arange(n) / SR
    env = 0.55 + 0.45 * np.sin(2 * np.pi * 4.0 * t + rng.uniform(0, 6)) ** 2
    x = sum(np.sin(2 * np.pi * f0 * k * t) / k for k in (1, 2, 3, 4))
    ramp = np.minimum(1, np.minimum(np.arange(n), np.arange(n)[::-1]) / (0.01 * SR))
    return 0.18 * x * env * ramp


def make_workspace(root: str | Path, episode_id: str = EPISODE) -> Path:
    root = Path(root)
    raw = root / "episodes" / episode_id / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7)
    n = int(DUR * SR)
    refs = {}
    for name, f0 in (("Leon", 120.0), ("Pei", 210.0)):
        x = 3e-4 * rng.standard_normal(n)
        for tr, a, b in TURNS:
            if tr == name:
                i, j = int(a * SR), int(b * SR)
                x[i:j] += _speech(j - i, f0, rng)
        path = raw / f"{name}.wav"
        sf.write(str(path), x.astype(np.float32), SR, subtype="PCM_16")
        refs[name] = MediaRef.probe(path)
    tl = new_timeline(SR, ["Leon", "Pei"])
    for name, ref in refs.items():
        tl = add_source_clip(tl, name, ref)
    project = Project({r.media_id: r for r in refs.values()}, tl)
    S = lambda s: int(round(s * SR))  # noqa: E731
    cut = lambda a, b: {"op": "cut", "start": S(a), "end": S(b), "tracks": None}  # noqa: E731
    edits = [
        Edit("e001", [cut(4.2, 5.3)], "pause", "停顿 1.5s → 0.4s", "停顿偏长，收紧到 0.4 秒", 0.95),
        Edit("e002", [{"op": "lift", "track": "Pei", "start": S(11.0), "end": S(11.4)}], "crosstalk",
             "Pei 单轨删除 0.4 秒", "压在 Leon 说话下的附和声", 0.8),
        Edit("e003", [cut(26.3, 30.7)], "content", "删除 4.4 秒 · 题外话",
             "这段和主线无关，后文没有再提到（测试数据）", 0.6, consequential=True),
        Edit("e004", [cut(44.3, 45.7)], "pause", "停顿 2.0s → 0.6s", "停顿偏长", 0.9),
        Edit("e005", [{"op": "track_gain", "track": "Leon", "gain_db": 3.0}], "loudness",
             "Leon 音轨 +3 dB", "两轨响度匹配", 0.95),
        Edit("e006", [cut(48.0, 48.6)], "filler", "口误重复 0.6 秒", "无意识重复", 0.7),
    ]
    words = {"Leon": [], "Pei": []}
    k = 0
    for tr, a, b in TURNS:
        t = a
        while t + 0.25 <= b:
            words[tr].append([round(t, 3), round(t + 0.25, 3), CHARS[k % len(CHARS)]])
            t += 0.3
            k += 1
    meta = {"title": "合成测试集", "demo": True, "demo_note": "合成测试数据", "raw_offset_s": 0.0}
    create_episode(Workspace(root), episode_id, meta, project, edits, {"tracks": words})
    return root


if __name__ == "__main__":
    make_workspace(sys.argv[1])
    print(f"synthetic workspace at {sys.argv[1]}")
