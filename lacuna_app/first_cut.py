"""AI first cut of a new episode: the S5 editor, run through the Claude API in raw-time windows.

The whole editor document (transcript with token ids + numeric features, ``features.build``) sits
in the cached system prompt, so every window is edited with the full conversation in view; each
request asks for the ops of one ~10-minute window. Ops come back through a strict tool and are
rewritten into the S5 op schema (``spikes/s5_first_cut/edit_ops.schema.json``) that
``ai_cut.convert_ops`` turns into reviewable edits. Only text and numbers are sent (D23, R001).

``RuleFirstCut`` is the offline fallback (no key / no SDK): pause tightening by the learned
EP001 targets only, so an imported episode is still reviewable.
"""
from __future__ import annotations

import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .ai_cut import TrackTokens
from .editor import PRICES, ClaudeEditorAdapter, error_message, find_api_key, sdk_installed

PROMPTS = Path(__file__).resolve().parent / "prompts"
WINDOW_S = 600.0
MIN_TAIL_S = 180.0              # a shorter last window is merged into the one before
CATEGORIES = ["pause", "disfluency", "repetition", "crosstalk", "content", "interjection_move",
              "single_track_noise"]
_POINT = {"type": ["string", "null"]}
_NUM = {"type": ["number", "null"]}
TOOL = {
    "name": "submit_ops",
    "description": "Submit every edit op for the requested raw-time window, in time order.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["notes", "ops"],
        "properties": {
            "notes": {"type": "string",
                      "description": "One or two sentences, Simplified Chinese: what this window is about and what you mainly cut."},
            "ops": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["op", "track", "category", "from", "to", "at", "target_s", "delta_s",
                                 "reason", "confidence"],
                    "properties": {
                        "op": {"type": "string", "enum": ["cut", "tighten_pause", "slip", "keep_flag"]},
                        "track": {"type": "string", "enum": ["L", "P", "both"]},
                        "category": {"type": "string", "enum": CATEGORIES},
                        "from": _POINT | {"description": "cut/slip/keep_flag: token id or raw seconds as a string"},
                        "to": _POINT | {"description": "cut/slip/keep_flag: token id or raw seconds as a string"},
                        "at": _POINT | {"description": "tighten_pause: raw seconds inside the pause, or the token id it follows"},
                        "target_s": _NUM | {"description": "tighten_pause: seconds of pause to keep"},
                        "delta_s": _NUM | {"description": "slip: seconds to move (positive = later)"},
                        "reason": {"type": "string", "description": "One short sentence, Simplified Chinese."},
                        "confidence": {"type": "number", "description": "0..1: probability Leon makes the same edit"},
                    },
                },
            },
        },
    },
}
_TOKEN = re.compile(r"^[LP]\d{6}$")

Progress = Callable[[float, str], None]


def system_prompt(extra_rules: str = "") -> str:
    """Brief + learned EP001 rules (+ rules learned from Leon's later reviews, if any)."""
    parts = [(PROMPTS / "first_cut_brief.txt").read_text(encoding="utf-8"),
             (PROMPTS / "learned_rules_ep001.txt").read_text(encoding="utf-8")]
    if extra_rules.strip():
        parts.append("RULES LEARNED FROM LEON'S LATER REVIEWS (newer than EP001; they win where they conflict)\n"
                     + extra_rules.strip())
    return "\n\n".join(parts)


def windows(duration: float, size: float = WINDOW_S) -> list[tuple[float, float]]:
    """[(start, end)] raw seconds covering the episode; the last window may run long."""
    out, t = [], 0.0
    while t < duration:
        out.append([t, min(t + size, duration)])
        t += size
    if len(out) > 1 and out[-1][1] - out[-1][0] < MIN_TAIL_S:
        tail = out.pop()
        out[-1][1] = tail[1]
    return [(a, b) for a, b in out]


def window_request(a: float, b: float, k: int, n: int) -> str:
    m = lambda s: f"{int(s // 60):02d}:{int(s % 60):02d}"  # noqa: E731
    return (f"请剪第 {k + 1}/{n} 段：原始时间 {a:.2f}–{b:.2f} 秒（{m(a)}–{m(b)}）。"
            f"Edit raw window {a:.2f}–{b:.2f} s only: output every op whose start lies in this window "
            "(an op may end slightly after it). Follow the brief and the learned rules; call submit_ops once.")


@dataclass
class FirstCutResult:
    ops_doc: dict
    usage: dict = field(default_factory=dict)      # summed over windows
    notes: list[str] = field(default_factory=list)


class FirstCutError(RuntimeError):
    pass


def _point(v: Any):
    if v is None:
        return None
    s = str(v).strip()
    if _TOKEN.match(s):
        return s
    return float(s)


def to_s5_ops(raw_ops: list[dict], tokens: dict[str, TrackTokens], a: float, b: float,
              last: bool) -> list[dict]:
    """Tool ops -> S5 schema ops, keeping those that start in [a, b): every op belongs to exactly one
    window, so a seam op answered by both neighbours is kept once."""
    out = []
    for o in raw_ops:
        try:
            kind = o["op"]
            d = {"op": kind, "track": o["track"], "category": o["category"],
                 "reason": str(o.get("reason") or "").strip(), "confidence": float(o.get("confidence") or 0.5)}
            if kind == "tighten_pause":
                d["at"] = _point(o.get("at"))
                d["target_s"] = float(o["target_s"])
                start = d["at"]
            else:
                d["from"], d["to"] = _point(o.get("from")), _point(o.get("to"))
                if d["from"] is None or d["to"] is None:
                    continue
                if kind == "slip":
                    d["delta_s"] = float(o["delta_s"])
                if kind == "keep_flag":
                    d["suggested"] = "cut"
                start = d["from"]
            if start is None:
                continue
            if isinstance(start, str):
                tr = tokens.get(start[0])
                if tr is None or start not in tr.ids:
                    continue
                start = tr.toks[tr.ids[start]]["start"]
        except (KeyError, TypeError, ValueError):
            continue
        if (a <= start or a == 0.0) and (start < b or last):
            out.append(d)
    return out


def _add_usage(total: dict, u: dict) -> None:
    for k in ("input_tokens", "output_tokens", "cost_usd", "seconds"):
        total[k] = round(total.get(k, 0) + (u.get(k) or 0), 4)
    total["model"] = u.get("model", total.get("model"))
    total["calls"] = total.get("calls", 0) + 1


class ClaudeFirstCut:
    """Runs the windows through Claude; `client` can be injected (tests use a fake)."""

    name = "claude"
    model = ClaudeEditorAdapter.model

    def __init__(self, api_key: str | None = None, client: Any = None, effort: str | None = None,
                 concurrency: int = 2):
        if api_key is None and client is None:
            api_key, _ = find_api_key()
        self.api_key = api_key
        self._client = client
        self.effort = effort or os.environ.get("LACUNA_FIRST_CUT_EFFORT", "high")
        self.concurrency = concurrency

    @property
    def available(self) -> bool:
        return self._client is not None or (bool(self.api_key) and sdk_installed())

    @property
    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key, timeout=900.0, max_retries=4)
        return self._client

    def request(self, system: str, doc: str, user: str) -> dict:
        return dict(model=self.model, max_tokens=64000,
                    system=[{"type": "text", "text": system},
                            {"type": "text", "text": doc, "cache_control": {"type": "ephemeral"}}],
                    output_config={"effort": self.effort}, tools=[TOOL], tool_choice={"type": "auto"},
                    messages=[{"role": "user", "content": user}])

    def _call(self, req: dict):
        with self.client.beta.messages.stream(betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                                              **req) as s:
            return s.get_final_message()

    def run_window(self, system: str, doc: str, a: float, b: float, k: int, n: int) -> tuple[list[dict], str, dict]:
        """(raw tool ops, notes, usage) for one window; raises FirstCutError with a Chinese message."""
        t0 = time.monotonic()
        try:
            resp = self._call(self.request(system, doc, window_request(a, b, k, n)))
        except Exception as e:      # noqa: BLE001
            raise FirstCutError(error_message(e).replace("，这次没有改动。", "")) from e
        usage = ClaudeEditorAdapter._usage(resp, time.monotonic() - t0)
        if resp.stop_reason == "refusal":
            raise FirstCutError(f"Claude 拒绝处理第 {k + 1} 段")
        for block in resp.content:
            if block.type == "tool_use" and block.name == "submit_ops":
                return list(block.input.get("ops") or []), str(block.input.get("notes") or ""), usage
        if resp.stop_reason == "max_tokens":
            raise FirstCutError(f"第 {k + 1} 段的回答太长被截断")
        raise FirstCutError(f"Claude 没有交回第 {k + 1} 段的剪辑")

    def run(self, doc: str, duration: float, tokens: dict[str, TrackTokens], episode: str,
            progress: Progress = lambda f, s: None, cache_dir: Path | None = None,
            cancelled: Callable[[], bool] = lambda: False, extra_rules: str = "") -> FirstCutResult:
        """All windows; finished windows are cached in `cache_dir` so a retry resumes."""
        import json

        system = system_prompt(extra_rules)
        wins = windows(duration)
        n = len(wins)
        results: dict[int, tuple[list[dict], str, dict]] = {}
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)
            for k in range(n):
                p = cache_dir / f"window_{k:02d}.json"
                if p.is_file():
                    d = json.loads(p.read_text(encoding="utf-8"))
                    if d.get("window") == list(wins[k]) and d.get("system_len") == len(system):
                        results[k] = (d["ops"], d["notes"], {})
        lock = threading.Lock()

        def report():
            progress(len(results) / n, f"AI 第一刀：已剪 {len(results)}/{n} 段（每段约 10 分钟）")

        def one(k: int):
            if cancelled():
                return
            a, b = wins[k]
            ops, notes, usage = self.run_window(system, doc, a, b, k, n)
            with lock:
                results[k] = (ops, notes, usage)
                if cache_dir:
                    (cache_dir / f"window_{k:02d}.json").write_text(json.dumps(
                        {"window": [a, b], "system_len": len(system), "ops": ops, "notes": notes,
                         "usage": usage}, ensure_ascii=False), encoding="utf-8")
            report()

        report()
        todo = [k for k in range(n) if k not in results]
        if todo:
            one(todo[0])            # first call alone: it writes the prompt cache the others read
            with ThreadPoolExecutor(max_workers=self.concurrency) as ex:
                for f in [ex.submit(one, k) for k in todo[1:]]:
                    f.result()      # re-raises the first failure
        if cancelled():
            raise FirstCutError("已取消")
        usage: dict = {}
        ops: list[dict] = []
        notes = []
        for k in range(n):
            raw, note, u = results[k]
            if u:
                _add_usage(usage, u)
            a, b = wins[k]
            ops += to_s5_ops(raw, tokens, a, b, last=k == n - 1)
            if note:
                notes.append(f"{int(a // 60)}–{int(b // 60)} 分：{note}")
        for i, o in enumerate(ops):
            o["id"] = f"op{i + 1:04d}"
        doc_out = {"episode": episode, "model": f"{self.model} / LACUNA first cut (effort {self.effort})",
                   "notes": "\n".join(notes), "ops": ops}
        return FirstCutResult(doc_out, usage, notes)


class RuleFirstCut:
    """Offline fallback: only floor-gap tightening with the learned EP001 pause targets (R1)."""

    name = "rules"
    available = True

    @staticmethod
    def target(prev: str, nxt: str, gap: float) -> float | None:
        if prev == "L" and nxt == "P":
            return 0.2 if gap >= 0.4 else None
        if prev == "P" and nxt == "L":
            return 0.5 if gap >= 0.8 else None
        if gap < 0.9:
            return None
        return 0.8 if gap < 2.0 else 1.0

    def run(self, doc: str, duration: float, tokens: dict[str, TrackTokens], episode: str,
            progress: Progress = lambda f, s: None, cache_dir: Path | None = None,
            cancelled: Callable[[], bool] = lambda: False, extra_rules: str = "") -> FirstCutResult:
        progress(0.0, "规则第一刀（没有 Claude）：收紧停顿")
        words = sorted((t["start"], t["end"], tag) for tag, tr in tokens.items() for t in tr.toks)
        ops = []
        end, who = None, None
        for s, e, tag in words:
            if end is not None and s - end > 0:
                gap = s - end
                tgt = self.target(who, tag, gap)
                if tgt is not None and gap - tgt >= 0.05:
                    ops.append({"id": f"op{len(ops) + 1:04d}", "op": "tighten_pause", "track": "both",
                                "at": round((end + s) / 2, 3), "target_s": tgt, "category": "pause",
                                "reason": f"{'Leon' if who == 'L' else 'Pei'}→{'Leon' if tag == 'L' else 'Pei'} "
                                          f"{gap:.2f}s→{tgt}s（规则）", "confidence": 0.6})
            if end is None or e > end:
                end, who = e, tag
        progress(1.0, "规则第一刀完成")
        return FirstCutResult({"episode": episode, "model": "rules (no Claude): pause targets only",
                               "notes": "没有 Claude：只按学到的停顿目标收紧了停顿。", "ops": ops},
                              {}, ["没有 Claude：只收紧了停顿。"])


def make_first_cut(kind: str = "auto"):
    if kind == "rules":
        return RuleFirstCut()
    c = ClaudeFirstCut()
    if kind == "claude" or c.available:
        return c
    return RuleFirstCut()
