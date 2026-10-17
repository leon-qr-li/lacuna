"""A stand-in for Claude's first cut on any imported episode (no key, no network).

It answers each window request the way the real editor does in shape and density, from the
episode's own tokens (`<workspace>/imports/<id>/tokens.json`): pause tightening at long floor
gaps, short cuts (disfluency / repetition) on one track, a long content cut on both tracks every
few minutes, an occasional slip and keep_flag, and one invalid op per window that must be dropped.
About 6 ops per minute (Sonnet's real EP001 cut had ~3.7, the S5 spike ~8.8).
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np


def _op(**kw):
    base = {"op": None, "track": None, "category": None, "from": None, "to": None, "at": None,
            "target_s": None, "delta_s": None, "reason": "", "confidence": 0.5}
    return base | kw


def window_ops(tokens: dict, a: float, b: float, seed: int) -> list[dict]:
    rng = np.random.default_rng(seed)
    ops: list[dict] = []
    tr = {tag: [t for t in toks if a <= t["start"] < b] for tag, toks in tokens.items()}
    words = sorted((t["start"], t["end"]) for toks in tr.values() for t in toks)
    gaps, end = [], None
    for s, e in words:
        if end is not None and s - end >= 1.0:
            gaps.append((end, s))
        end = e if end is None else max(end, e)
    for m0 in np.arange(a, b, 60.0):
        mine = [g for g in gaps if m0 <= g[0] < m0 + 60]
        for g0, g1 in mine[:2]:
            ops.append(_op(op="tighten_pause", track="both", category="pause", at=f"{(g0 + g1) / 2:.2f}",
                           target_s=0.6, reason=f"空白 {g1 - g0:.1f} 秒，收到 0.6 秒", confidence=0.85))
        for _ in range(3):
            tag = "L" if rng.random() < 0.5 else "P"
            cand = [t for t in tr[tag] if m0 <= t["start"] < m0 + 60]
            if len(cand) < 20:
                continue
            i = int(rng.integers(0, len(cand) - 16))
            j = i + int(rng.integers(2, 15))
            cat = str(rng.choice(["disfluency", "repetition", "content"]))
            ops.append(_op(op="cut", track=tag, category=cat, **{"from": cand[i]["id"], "to": cand[j]["id"]},
                           reason={"disfluency": "口误重说，留后一遍", "repetition": "同一个意思说了两遍",
                                   "content": "离题的一小段"}[cat], confidence=round(float(rng.uniform(0.3, 0.95)), 2)))
        if int(m0 // 60) % 7 == 3:
            s = m0 + float(rng.uniform(5, 20))
            ops.append(_op(op="cut", track="both", category="content", **{"from": f"{s:.2f}", "to": f"{s + float(rng.uniform(20, 45)):.2f}"},
                           reason="这段题外话和主线无关，后面没有再提", confidence=round(float(rng.uniform(0.3, 0.7)), 2)))
        if int(m0 // 60) % 5 == 1 and tr["P"]:
            t = tr["P"][int(rng.integers(len(tr["P"])))]
            ops.append(_op(op="slip", track="P", category="interjection_move", **{"from": t["id"], "to": t["id"]},
                           delta_s=0.4, reason="插话挪到 Leon 停顿处", confidence=0.6))
        if int(m0 // 60) % 6 == 2 and tr["L"]:
            t = tr["L"][int(rng.integers(len(tr["L"])))]
            ops.append(_op(op="keep_flag", track="L", category="content", **{"from": t["id"], "to": t["id"]},
                           reason="拿不准，留给 Leon", confidence=0.4))
    ops.append(_op(op="cut", track="L", category="disfluency", **{"from": "L999999", "to": "L999999"},
                   reason="不存在的 token，会被丢掉", confidence=0.5))
    return ops


class _Stream:
    def __init__(self, resp):
        self.resp = resp

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.resp


class FakeLongFirstCut:
    """`client.beta.messages.stream(...)` for ClaudeFirstCut, reading the episode's tokens."""

    def __init__(self, workspace: Path, delay: float = 2.0):
        self.ws, self.delay = Path(workspace), delay
        self._re = re.compile(r"原始时间 ([\d.]+)–([\d.]+) 秒")
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kw):
        a, b = map(float, self._re.search(kw["messages"][0]["content"]).groups())
        episode = re.match(r"# (\S+) 剪辑输入", kw["system"][1]["text"]).group(1)
        tokens = json.loads((self.ws / "imports" / episode / "tokens.json").read_text(encoding="utf-8"))["tracks"]
        time.sleep(self.delay)
        ops = window_ops(tokens, a, b, seed=int(a))
        inp = {"notes": f"合成长测试：{len(ops)} 个改动。", "ops": ops}
        return _Stream(SimpleNamespace(
            stop_reason="tool_use", model=kw["model"], _request_id="req_fake",
            content=[SimpleNamespace(type="tool_use", name="submit_ops", input=inp)],
            usage=SimpleNamespace(input_tokens=600, output_tokens=12000, cache_creation_input_tokens=60000,
                                  cache_read_input_tokens=0)))
