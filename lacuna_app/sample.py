"""LACUNA 示例节目 (new-user batch, Leon 2026-10-22, Q4A / Q5A): a show of its own with one prepared episode in
the interface language, where a new person tries the whole flow (review → listen → music → export) in a few
minutes before importing their own recording.

The recording is shared: one read-only copy per language under ``<root>/sample/v<VERSION>/<lang>/raw``, built
once; every person's sample show gets only its own copy of the episode's edit list (state, transcript), which
points at those files. So it takes almost no disk, the original audio is never written, and "重置示例" just
copies the episode files again. The show is marked ``sample`` in the site database: it doesn't count against
the plan's show limit, and audio-hour metering (batch 5) must skip it too.

Until Leon and Pei record the real sample (Q3), the recording is a placeholder: two speech-like tones under a
scripted conversation whose transcript reads properly, with a first cut that shows each kind of edit once.
Replacing it: put the real episode here and bump VERSION (old masters stay until nobody's sample uses them).
"""
from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import soundfile as sf

from . import show
from .store import atomic_write_json

VERSION = 1
EPISODE = "SAMPLE_01"
LANGS = ("zh", "en")
SR = 16000
NAME = {"zh": "LACUNA 示例节目", "en": "LACUNA Sample Show"}  # i18n-ignore
TITLE = {"zh": "示例 · 电影夜", "en": "Sample · Movie Night"}  # i18n-ignore
HOSTS = {"zh": ("小林", "阿乔"), "en": ("Sam", "Alex")}  # i18n-ignore
ABOUT = {"zh": "两位主持人聊一部刚看过的电影。（LACUNA 示例节目，录音为占位音频）",  # i18n-ignore
         "en": "Two hosts talk about a film they just watched. (LACUNA sample show, placeholder recording)"}

# (host 0/1, text, seconds of silence after). Placeholder script following the dialogue outline: a restart,
# fillers, a long pause, a tangent (the one content cut to review), laughing over each other, a correction.
SCRIPT = {
    "zh": [
        (0, "大家好 欢迎收听 今天我们 今天我们聊一部 我们两个都看过的电影", 0.6),  # i18n-ignore
        (1, "对 就是上周末一起看的那部", 0.5),  # i18n-ignore
        (0, "我觉得 嗯 它的开头 呃 真的 真的 真的很抓人", 0.7),  # i18n-ignore
        (1, "那个演员叫什么来着", 4.6),  # i18n-ignore
        (1, "想起来了 是演过很多文艺片的那位", 0.6),  # i18n-ignore
        (0, "说到这个 我那天停车找了半天 我表哥的车也停在那边 后来还被贴了罚单", 0.4),  # i18n-ignore
        (1, "好了 说回电影", 0.6),  # i18n-ignore
        (0, "结尾那场戏你哭了吧", 0.2),  # i18n-ignore
        (1, "哈哈 你也哭了", 0.6),  # i18n-ignore
        (1, "我给它打八分 不对 是九分", 0.7),  # i18n-ignore
        (0, "我也九分 下期见", 0.8),  # i18n-ignore
    ],
    "en": [
        (0, "Hi everyone so today we're so today we are talking about a film we both saw", 0.6),
        (1, "Right the one we watched last weekend", 0.5),
        (0, "I thought um the opening was uh it was it was it was really gripping", 0.7),
        (1, "What was the lead actor called again", 4.6),
        (1, "Oh I remember the one from all those indie films", 0.6),
        (0, "Speaking of which parking took forever my cousin's car was there too and he got a ticket", 0.4),
        (1, "Anyway back to the movie", 0.6),
        (0, "You cried at the ending right", 0.2),
        (1, "Ha you did too", 0.6),
        (1, "I'd give it an eight no wait a nine", 0.7),
        (0, "Nine for me too see you next time", 0.8),
    ],
}
# what the first cut does: (turn, words, op, category, reason) - the words are found inside that turn
CUTS = {
    "zh": [
        (0, "今天我们", "cut", "repetition", "开头说了两遍，保留第二遍"),  # i18n-ignore
        (2, "嗯", "cut", "disfluency", "嗯"),  # i18n-ignore
        (2, "呃", "cut", "disfluency", "呃"),  # i18n-ignore
        (2, "真的 真的", "cut", "repetition", "「真的」说了三遍，留一遍"),  # i18n-ignore
        (5, "说到这个 我那天停车找了半天 我表哥的车也停在那边 后来还被贴了罚单", "cut", "content",  # i18n-ignore
         "停车和罚单是题外话，后面没有再提"),  # i18n-ignore
        (9, "八分 不对 是", "cut", "repetition", "说错又纠正，留纠正后的"),  # i18n-ignore
    ],
    "en": [
        (0, "so today we're", "cut", "repetition", "Restarted the sentence, keep the second take"),
        (2, "um", "cut", "disfluency", "um"),
        (2, "uh", "cut", "disfluency", "uh"),
        (2, "it was it was", "cut", "repetition", "\"it was\" said three times, keep one"),
        (5, "Speaking of which parking took forever my cousin's car was there too and he got a ticket", "cut",
         "content", "The parking story is a tangent and never comes back"),
        (9, "an eight no wait", "cut", "repetition", "Said a score, then corrected it; keep the correction"),
    ],
}
LONG_PAUSE = 3      # the turn after which the long pause is tightened


def master(root: str | Path, lang: str) -> Path:
    """The shared sample for `lang` (built on first use): its workspace folder, holding the one episode."""
    lang = lang if lang in LANGS else "en"
    base = Path(root) / "sample" / f"v{VERSION}" / lang
    ws = base / "ws"
    if not (ws / "episodes" / EPISODE / "state.json").is_file():
        _build(base, lang)
    return ws


def give(root: str | Path, space: str | Path, lang: str) -> None:
    """Make `space` (a new show's folder) the sample show: profile, and a fresh copy of the episode."""
    lang = lang if lang in LANGS else "en"
    space = Path(space)
    a, b = HOSTS[lang]
    profile = show.normalise({"setup_done": True, "show_name": NAME[lang], "about": ABOUT[lang], "language": lang,
                              "hosts": [{"tag": "A", "name": a}, {"tag": "B", "name": b}]}, strict=False)
    atomic_write_json(space / show.FILE, profile)
    reset(root, space, lang)


def reset(root: str | Path, space: str | Path, lang: str) -> None:
    """重置示例: the episode back to the moment the first cut was done (the shared recording is untouched)."""  # i18n-ignore
    src = master(root, lang) / "episodes" / EPISODE
    dst = Path(space) / "episodes" / EPISODE
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def _turns(lang: str):
    """[(host, start, end, word)] with times: one token per character (zh) or word (en)."""
    step, size = (0.3, 0.25) if lang == "zh" else (0.42, 0.36)
    out, t = [], 0.6
    for i, (host, text, gap) in enumerate(SCRIPT[lang]):
        words = [c for c in text if c != " "] if lang == "zh" else text.split()
        toks = []
        for w in words:
            toks.append((host, round(t, 3), round(t + size, 3), w))
            t += step
        out.append(toks)
        t += gap
    return out, t + 0.5


def _speech(n: int, f0: float, rng) -> np.ndarray:
    t = np.arange(n) / SR
    env = 0.55 + 0.45 * np.sin(2 * np.pi * 4.0 * t + rng.uniform(0, 6)) ** 2
    x = sum(np.sin(2 * np.pi * f0 * k * t) / k for k in (1, 2, 3, 4))
    ramp = np.minimum(1, np.minimum(np.arange(n), np.arange(n)[::-1]) / (0.01 * SR))
    return 0.16 * x * env * ramp


def _build(base: Path, lang: str) -> None:
    from lacuna_core import MediaRef
    from .ai_cut import TrackTokens, build_episode
    from .episode import create_episode
    from .store import Workspace

    turns, dur = _turns(lang)
    names = HOSTS[lang]
    tags = ("A", "B")
    tmp = base.with_name(base.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    raw = tmp / "raw"
    raw.mkdir(parents=True)
    rng = np.random.default_rng(11)
    n = int(dur * SR)
    refs = {}
    for h, (name, f0) in enumerate(zip(names, (130.0, 205.0))):
        x = 3e-4 * rng.standard_normal(n)
        for toks in turns:
            if toks and toks[0][0] == h:
                i, j = int(toks[0][1] * SR), int(toks[-1][2] * SR)
                x[i:j] += _speech(j - i, f0, rng)
        path = raw / f"{name}.wav"
        sf.write(str(path), x.astype(np.float32), SR, subtype="PCM_16")
        refs[name] = path
    # the episode references the files where they will live, so write the audio there first
    final_raw = base / "raw"
    shutil.rmtree(base, ignore_errors=True)
    base.mkdir(parents=True)
    shutil.move(str(raw), str(final_raw))
    shutil.rmtree(tmp, ignore_errors=True)
    media = {name: MediaRef.probe(final_raw / f"{name}.wav") for name in names}

    ids: dict[int, list[str]] = {}
    tracks: dict[str, list[dict]] = {t: [] for t in tags}
    for ti, toks in enumerate(turns):
        ids[ti] = []
        for k, (h, a, b, w) in enumerate(toks):
            tid = f"{tags[h]}{len(tracks[tags[h]]):06d}"
            tracks[tags[h]].append({"id": tid, "t": w, "start": a, "end": b, "pause_after": 0.0, "flag": None})
            ids[ti].append(tid)
    ops = []
    for i, (ti, words, op, cat, reason) in enumerate(CUTS[lang], 1):
        seq = [x[3] for x in turns[ti]]
        want = [c for c in words if c != " "] if lang == "zh" else words.split()
        at = next(k for k in range(len(seq)) if seq[k:k + len(want)] == want)
        host = tags[turns[ti][0][0]]
        ops.append({"id": f"op{i:04d}", "op": op, "track": host if cat != "content" else "both",
                    "from": ids[ti][at], "to": ids[ti][at + len(want) - 1], "category": cat, "reason": reason,
                    "confidence": 0.55 if cat == "content" else 0.85})
    last = turns[LONG_PAUSE][-1][2]
    ops.append({"id": f"op{len(ops) + 1:04d}", "op": "tighten_pause", "track": "both", "at": round(last + 2.3, 3),
                "target_s": 0.6, "category": "pause",
                "reason": "空白 4.6 秒，收到 0.6 秒" if lang == "zh" else "A 4.6 s silence, tightened to 0.6 s",  # i18n-ignore
                "confidence": 0.85})
    doc = {"episode": EPISODE, "model": "sample", "ops": ops}
    tokens = {t: TrackTokens(v) for t, v in tracks.items()}
    project, edits, transcript, _ = build_episode(media, doc, tokens, 0.0, None, None, dict(zip(tags, names)))
    meta = {"title": TITLE[lang], "demo": False, "raw_offset_s": 0.0, "source": "sample", "language": lang}
    create_episode(Workspace(base / "ws"), EPISODE, meta, project, edits, transcript)
