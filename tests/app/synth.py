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


def write_raw(raw: Path) -> dict[str, MediaRef]:
    """Two synthetic host tracks (speech-like tones during TURNS, faint noise elsewhere)."""
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
    return refs


def words_by_track() -> dict[str, list[list]]:
    """[start, end, char] per track: one 0.25 s "word" every 0.3 s through each turn."""
    words = {"Leon": [], "Pei": []}
    k = 0
    for tr, a, b in TURNS:
        t = a
        while t + 0.25 <= b:
            words[tr].append([round(t, 3), round(t + 0.25, 3), CHARS[k % len(CHARS)]])
            t += 0.3
            k += 1
    return words


def tokens_doc() -> dict:
    """The words as an S5 token file (ids L000000 / P000000, raw seconds)."""
    out = {}
    for name, ws in words_by_track().items():
        tag = name[0]
        out[tag] = [{"id": f"{tag}{i:06d}", "t": w, "start": s, "end": e, "pause_after": 0.0, "flag": None}
                    for i, (s, e, w) in enumerate(ws)]
    return {"episode": "SYNTH", "time_base": "raw seconds", "tracks": out}


def tok(tag: str, t: float) -> str:
    """Id of the token of track `tag` that starts at or just before raw time t."""
    toks = tokens_doc()["tracks"][tag]
    return max((x for x in toks if x["start"] <= t + 1e-9), key=lambda x: x["start"])["id"]


def ai_ops_doc() -> dict:
    """A small AI first cut over the synthetic conversation (schema of edit_ops.schema.json)."""
    def op(i, **kw):
        return {"id": f"op{i:04d}", **kw}
    return {"episode": "SYNTH", "model": "synthetic", "ops": [
        op(1, op="tighten_pause", track="both", at=4.2, target_s=0.4, category="pause",
           reason="两人之间的空白 1.5 秒，收到 0.4 秒", confidence=0.9),
        op(2, op="cut", track="P", **{"from": tok("P", 11.0), "to": tok("P", 11.0)}, category="crosstalk",
           reason="压在 Leon 说话下的附和", confidence=0.8),
        op(3, op="cut", track="L", **{"from": tok("L", 18.2), "to": tok("L", 20.0)}, category="repetition",
           reason="同一句话说了两遍，保留第二遍", confidence=0.7),
        op(4, op="slip", track="P", **{"from": tok("P", 22.3), "to": tok("P", 22.6)}, delta_s=0.5,
           category="interjection_move", reason="嗯 挪到 Leon 句末的停顿", confidence=0.4),
        op(5, op="cut", track="both", **{"from": tok("L", 26.5), "to": tok("L", 29.6)}, category="content",
           reason="这段题外话和主线无关，后面没有再提", confidence=0.55),
        op(6, op="keep_flag", track="L", **{"from": tok("L", 36.5), "to": tok("L", 37.7)}, suggested="cut",
           category="content", reason="可能离题，但也许后面会回扣", confidence=0.5),
        op(7, op="tighten_pause", track="both", at=44.2, target_s=0.6, category="pause",
           reason="空白 2.0 秒，收到 0.6 秒", confidence=0.85),
        op(8, op="cut", track="L", **{"from": tok("L", 48.1), "to": tok("L", 48.4)}, category="disfluency",
           reason="嗯 呃 口误", confidence=0.75),
        op(9, op="cut", track="both", **{"from": 56.0, "to": 57.0}, category="content",
           reason="窗口外", confidence=0.5),
    ]}


AI_EPISODE = "EP_AI_合成"
AI_TITLE = "合成 · AI 第一刀"
AI_WINDOW = (1.0, 0.9)    # start s, minutes -> raw 1.0 .. 55.0 s


def make_ai_workspace(root: str | Path, episode_id: str = AI_EPISODE) -> Path:
    """Workspace with one episode built by scripts/make_ai_episode.py from `ai_ops_doc`."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import make_ai_episode
    from lacuna_app.ai_cut import TrackTokens
    root = Path(root)
    refs = write_raw(root / "episodes" / episode_id / "raw")
    tokens = {tag: TrackTokens(t) for tag, t in tokens_doc()["tracks"].items()}
    w0, minutes = AI_WINDOW
    project, edits, transcript, report = make_ai_episode.build(refs, ai_ops_doc(), tokens, w0, w0 + minutes * 60)
    meta = {"title": AI_TITLE, "demo": False, "raw_offset_s": w0, "source": "ai_cut:synthetic"}
    create_episode(Workspace(root), episode_id, meta, project, edits, transcript)
    return root


def seed_learning(root: str | Path) -> None:
    """A decision snapshot from an earlier (imaginary) episode: Leon restored four of Pei's small
    stumbles, which is enough for one candidate rule on the learning page."""
    from lacuna_app.learning import Decision, Learning
    ds = [Decision(episode="EP_旧一集", edit_id=f"a{i:04d}", source="first_cut", kind="disfluency", category="filler",
                   host="Pei", verdict="restored", how="single", confidence=0.6, length_s=0.6, speech_s=0.5,
                   text=t, reason="口误", raw=[60.0 * i, 60.0 * i + 0.6])
          for i, t in enumerate(("呃就是", "对这也就就", "嗯那个", "我我觉得"), 1)]
    Learning(Workspace(root)).save_decisions("EP_旧一集", ds)


def make_workspace(root: str | Path, episode_id: str = EPISODE) -> Path:
    root = Path(root)
    refs = write_raw(root / "episodes" / episode_id / "raw")
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
    words = words_by_track()
    meta = {"title": "合成测试集", "demo": True, "demo_note": "合成测试数据", "raw_offset_s": 0.0}
    create_episode(Workspace(root), episode_id, meta, project, edits, {"tracks": words})
    return root


def write_recordings(folder: str | Path) -> dict[str, Path]:
    """The two synthetic raw tracks in a plain folder (as Riverside would leave them), for imports."""
    refs = write_raw(Path(folder))
    return {name: Path(r.path) for name, r in refs.items()}


def fake_asr(tag: str, x, progress=lambda f, s: None) -> dict:
    """Stand-in for lacuna_app.asr.transcribe: one VAD segment per turn, the synthetic words as
    Paraformer tokens; SenseVoice agrees except it hears an extra 嗯 after the first word."""
    name = {"L": "Leon", "P": "Pei"}[tag]
    words = words_by_track()[name]
    segs = []
    for tr, a, b in TURNS:
        if tr != name:
            continue
        toks = [{"t": w, "start": s, "end": e} for s, e, w in words if a <= s < b]
        sv = [dict(t) for t in toks]
        if len(segs) == 0 and sv:
            sv.insert(1, {"t": "嗯", "start": sv[0]["end"], "end": sv[0]["end"] + 0.05})
        text = "".join(t["t"] for t in toks)
        segs.append({"start": round(max(a - 0.2, 0), 3), "end": round(b + 0.2, 3),
                     "par": {"text": text, "tokens": toks},
                     "sv": {"text": "".join(t["t"] for t in sv), "event": "Speech", "emotion": "NEUTRAL", "tokens": sv}})
        progress(b / DUR, f"逐字识别 {int(b)} 秒")
    return {"audio_s": round(len(x) / SR, 3), "segments": segs}


if __name__ == "__main__":
    (make_ai_workspace if "--ai" in sys.argv else make_workspace)(sys.argv[1])
    print(f"synthetic workspace at {sys.argv[1]}")
