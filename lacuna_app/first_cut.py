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

import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import show
from .ai_cut import TrackTokens
from .editor import ClaudeEditorAdapter, error_message, find_api_key, sdk_installed
from .i18n import AI_NAME_RULE, in_reply_language, lang, tr
from .store import atomic_write_json, read_json

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
_TOKEN = re.compile(r"^[A-Z]\d{6}$")       # <track tag><index>, e.g. L000812


def tool_for(tags: list[str], legacy: bool = True) -> dict:
    """TOOL with the episode's own track tags (+ "both" = every track)."""
    t = json.loads(json.dumps(TOOL))
    props = t["input_schema"]["properties"]["ops"]["items"]["properties"]
    props["track"]["enum"] = list(tags) + ["both"]
    if not legacy:
        props["confidence"]["description"] = "0..1: probability the show's editor makes the same edit"
    return t

Progress = Callable[[float, str], None]


def system_prompt(extra_rules: str = "", profile: dict | None = None, language: str = "zh") -> str:
    """Brief + learned EP001 rules (+ rules learned from Leon's later reviews, if any).

    Another show (`profile` from show.py, not Leon's): the same brief with its own name, tracks and
    per-host strictness, LACUNA's default rules instead of Leon's EP001 calibration, then its own
    learned rules. An English episode (any show) gets the English brief and defaults: Leon's EP001
    calibration is about Chinese speech."""
    if language == "en":
        return generic_prompt(extra_rules, profile or show.LEGACY, "en")
    if not show.is_legacy(profile):
        return generic_prompt(extra_rules, profile)
    parts = [(PROMPTS / "first_cut_brief.txt").read_text(encoding="utf-8"),
             (PROMPTS / "learned_rules_ep001.txt").read_text(encoding="utf-8")]
    if show.legacy_level_note():
        parts.append(show.legacy_level_note())
    if extra_rules.strip():
        parts.append("RULES LEARNED FROM LEON'S LATER REVIEWS (newer than EP001; they win where they conflict)\n"
                     + extra_rules.strip())
    return "\n\n".join(parts)


def generic_prompt(extra_rules: str, profile: dict, language: str = "zh") -> str:
    tags = [h["tag"] for h in profile["hosts"]]
    suffix = "_en" if language == "en" else ""
    brief = (PROMPTS / ("first_cut_brief_en.txt" if suffix else "first_cut_brief_generic.txt")).read_text(encoding="utf-8")
    for k, v in {"<<SHOW>>": show.describe_en(profile).rsplit(" (", 1)[0],
                 "<<TRACKS>>": ", ".join(f"{h['name']} = track {h['tag']}" for h in profile["hosts"]),
                 "<<TOKEN_EXAMPLES>>": " / ".join(f'"{t}000812"' for t in tags[:2]),
                 "<<T1>>": tags[0], "<<TRACK_LIST>>": ", ".join(tags),
                 "<<STYLES>>": show.style_lines(profile)}.items():
        brief = brief.replace(k, v)
    parts = [brief, (PROMPTS / f"first_cut_defaults{suffix}.txt").read_text(encoding="utf-8")]
    if extra_rules.strip():
        parts.append("RULES LEARNED FROM THE EDITOR'S REVIEWS OF THIS SHOW (they win where they conflict "
                     "with the defaults)\n" + extra_rules.strip())
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


def window_request(a: float, b: float, k: int, n: int, who: str = "Leon") -> str:
    m = lambda s: f"{int(s // 60):02d}:{int(s % 60):02d}"  # noqa: E731
    return (f"请剪第 {k + 1}/{n} 段：原始时间 {a:.2f}–{b:.2f} 秒（{m(a)}–{m(b)}）。"  # i18n-ignore
            f"Edit raw window {a:.2f}–{b:.2f} s only: output every op whose start lies in this window "
            "(an op may end slightly after it). Follow the brief and the learned rules; call submit_ops once."
            + (f" {who} reads LACUNA in English: write every reason and the notes in English." if lang() == "en" else ""))


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
    # Opus refuses whole-episode first-cut requests ("reasoning_extraction", tested on EP001 with
    # opus-5-5 and opus-5, every prompt variant); Sonnet 5.5 does the job, at half the price. A
    # refused window is retried once on FALLBACK_MODEL whatever the configured model.
    MODEL = "claude-sonnet-5-5"
    FALLBACK_MODEL = "claude-sonnet-5-5"

    def __init__(self, api_key: str | None = None, client: Any = None, effort: str | None = None,
                 concurrency: int = 3, model: str | None = None):
        if api_key is None and client is None:
            api_key, _ = find_api_key()
        self.api_key = api_key
        self._client = client
        self.effort = effort or os.environ.get("LACUNA_FIRST_CUT_EFFORT", "high")
        self.concurrency = concurrency
        self.model = model or os.environ.get("LACUNA_FIRST_CUT_MODEL", self.MODEL)
        self.on_usage: Callable[[dict], None] = lambda u: None
        self.names: dict[str, str] = {"L": "Leon", "P": "Pei"}   # track tag -> host (set by the importer)
        self.show: dict | None = None                            # the workspace's show (prompt), None = Leon's
        self.language = "zh"                                     # the episode's (set by the importer)
        self.batch = False                                       # Batch API, half price (set by the importer)
        self._sleep = time.sleep

    @property
    def available(self) -> bool:
        return self._client is not None or (bool(self.api_key) and sdk_installed())

    @property
    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key, timeout=900.0, max_retries=4)
        return self._client

    def request(self, system: str, doc: str, user: str, model: str | None = None) -> dict:
        return dict(model=model or self.model, max_tokens=64000,
                    system=[{"type": "text", "text": system + AI_NAME_RULE},
                            {"type": "text", "text": doc, "cache_control": {"type": "ephemeral"}}],
                    output_config={"effort": self.effort}, tools=[in_reply_language(tool_for(list(self.names), show.is_legacy(self.show) and self.language != "en"))],
                    tool_choice={"type": "auto"}, messages=[{"role": "user", "content": user}])

    def _call(self, req: dict):
        extra = ({"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
                 if "opus" in req["model"] else {})
        with self.client.beta.messages.stream(**extra, **req) as s:
            return s.get_final_message()

    def _who(self) -> str:
        return "Leon" if show.is_legacy(self.show) and self.language != "en" else "The editor"

    @staticmethod
    def _ops(resp, k: int) -> tuple[list[dict], str]:
        for block in resp.content:
            if block.type == "tool_use" and block.name == "submit_ops":
                return list(block.input.get("ops") or []), str(block.input.get("notes") or "")
        if resp.stop_reason == "max_tokens":
            raise FirstCutError(tr("第 {p0} 段的回答太长被截断", p0=k + 1))
        raise FirstCutError(tr("LACUNA 没有交回第 {p0} 段的剪辑", p0=k + 1))

    def run_window(self, system: str, doc: str, a: float, b: float, k: int, n: int) -> tuple[list[dict], str, dict]:
        """(raw tool ops, notes, usage) for one window; raises FirstCutError with a Chinese message."""
        model = self.model
        while True:
            t0 = time.monotonic()
            try:
                resp = self._call(self.request(system, doc, window_request(a, b, k, n, self._who()), model))
            except Exception as e:      # noqa: BLE001
                raise FirstCutError(error_message(e, tail="")) from e
            usage = ClaudeEditorAdapter._usage(resp, time.monotonic() - t0)
            if resp.stop_reason != "refusal":
                break
            cat = getattr(getattr(resp, "stop_details", None), "category", None)
            self.on_usage(usage | {"refusal": cat or True})      # refused calls are billed too
            if model == self.FALLBACK_MODEL:
                raise FirstCutError(tr("LACUNA 拒绝处理第 {p0} 段", p0=k + 1) + (f"（{cat}）" if cat else ""))
            model = self.FALLBACK_MODEL
        self.on_usage(usage)
        return (*self._ops(resp, k), usage)

    BATCH_POLL_S = 30.0
    BATCH_MAX_S = 24 * 3600.0           # the API gives up on a batch after 24 hours too

    def run_batch(self, system: str, doc: str, wins: list[tuple[float, float]], todo: list[int],
                  progress: Callable[[str], None], cancelled: Callable[[], bool]) -> dict[int, tuple[list[dict], str, dict]]:
        """Half-price path (ai_settings.first_cut_batch): every window in one Message Batch. Returns the windows it
        finished; one it did not (refused, errored, expired, unreadable) is cut the normal way afterwards."""
        n = len(wins)
        reqs = [{"custom_id": f"w{k:02d}", "params": self.request(system, doc, window_request(*wins[k], k, n, self._who()))}
                for k in todo]
        t0 = time.monotonic()
        try:
            batch = self.client.messages.batches.create(requests=reqs)
        except Exception as e:      # noqa: BLE001
            raise FirstCutError(error_message(e, tail="")) from e
        while batch.processing_status != "ended":
            waited = time.monotonic() - t0
            if cancelled() or waited > self.BATCH_MAX_S:
                try:
                    self.client.messages.batches.cancel(batch.id)
                except Exception:   # noqa: BLE001 - it expires on its own
                    pass
                return {}
            progress(tr("AI 第一刀（省钱模式）：排队处理中，已等 {m} 分钟，通常 10–30 分钟", m=int(waited // 60)))
            end = time.monotonic() + self.BATCH_POLL_S
            while time.monotonic() < end and not cancelled():
                self._sleep(min(1.0, self.BATCH_POLL_S))
            try:
                batch = self.client.messages.batches.retrieve(batch.id)
            except Exception:       # noqa: BLE001 - a network blip: ask again next round
                continue
        done: dict[int, tuple[list[dict], str, dict]] = {}
        seconds = time.monotonic() - t0
        try:
            results = list(self.client.messages.batches.results(batch.id))
        except Exception:           # noqa: BLE001 - cut them the normal way
            return {}
        for r in results:
            k = int(r.custom_id[1:])
            if getattr(r.result, "type", "") != "succeeded":
                continue
            msg = r.result.message
            usage = ClaudeEditorAdapter._usage(msg, seconds, batch=True)
            if msg.stop_reason == "refusal":
                cat = getattr(getattr(msg, "stop_details", None), "category", None)
                self.on_usage(usage | {"refusal": cat or True})
                continue
            self.on_usage(usage)
            try:
                done[k] = (*self._ops(msg, k), usage)
            except FirstCutError:
                continue
        return done

    def run(self, doc: str, duration: float, tokens: dict[str, TrackTokens], episode: str,
            progress: Progress = lambda f, s: None, cache_dir: Path | None = None,
            cancelled: Callable[[], bool] = lambda: False, extra_rules: str = "") -> FirstCutResult:
        """All windows; finished windows are cached in `cache_dir` so a retry resumes."""
        system = system_prompt(extra_rules, self.show, self.language)
        wins = windows(duration)
        n = len(wins)
        results: dict[int, tuple[list[dict], str, dict]] = {}
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)
            for k in range(n):
                p = cache_dir / f"window_{k:02d}.json"
                if p.is_file():
                    try:
                        d = read_json(p)
                    except (OSError, ValueError):
                        continue            # torn by a crash mid-write: cut this window again
                    if d.get("window") == list(wins[k]) and d.get("system_len") == len(system):
                        results[k] = (d["ops"], d["notes"], {})
        lock = threading.Lock()

        def report():
            progress(len(results) / n, tr("AI 第一刀：已剪 {p0}/{n} 段（每段约 10 分钟录音）", p0=len(results), n=n))

        def keep(k: int, ops: list[dict], notes: str, usage: dict):
            a, b = wins[k]
            with lock:
                results[k] = (ops, notes, usage)
                if cache_dir:
                    atomic_write_json(cache_dir / f"window_{k:02d}.json",
                                      {"window": [a, b], "system_len": len(system), "ops": ops, "notes": notes,
                                       "usage": usage})

        def one(k: int):
            if cancelled():
                return
            a, b = wins[k]
            keep(k, *self.run_window(system, doc, a, b, k, n))
            report()

        report()
        todo = [k for k in range(n) if k not in results]
        if todo and self.batch:
            for k, r in self.run_batch(system, doc, wins, todo, lambda s: progress(len(results) / n, s), cancelled).items():
                keep(k, *r)
            report()
            todo = [k for k in todo if k not in results]
        if todo and not cancelled():
            one(todo[0])            # first call alone: it writes the prompt cache the others read
            with ThreadPoolExecutor(max_workers=self.concurrency) as ex:
                for f in [ex.submit(one, k) for k in todo[1:]]:
                    f.result()      # re-raises the first failure
        if cancelled():
            raise FirstCutError(tr("已取消"))
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
                notes.append(tr("{p0}–{p1} 分：{note}", p0=int(a // 60), p1=int(b // 60), note=note))
        for i, o in enumerate(ops):
            o["id"] = f"op{i + 1:04d}"
        models = sorted({u.get("model") for _, _, u in results.values() if u.get("model")} or {self.model})
        doc_out = {"episode": episode, "model": f"{' + '.join(models)} / LACUNA first cut (effort {self.effort}"
                                                f"{', batch' if self.batch else ''})",
                   "notes": "\n".join(notes), "ops": ops}
        return FirstCutResult(doc_out, usage, notes)


class RuleFirstCut:
    """Offline fallback: only floor-gap tightening with the learned EP001 pause targets (R1)."""

    name = "rules"
    available = True

    def __init__(self):
        self.names: dict[str, str] = {"L": "Leon", "P": "Pei"}

    @staticmethod
    def target(prev: str, nxt: str, gap: float) -> float | None:
        # Leon -> Pei / Pei -> Leon: measured on EP001 (tags L and P are only ever Leon's and Pei's)
        if prev == "L" and nxt == "P":
            return 0.2 if gap >= 0.4 else None
        if prev == "P" and nxt == "L":
            return 0.5 if gap >= 0.8 else None
        if prev != nxt:                      # any other change of speaker: a natural reply gap
            return 0.4 if gap >= 0.7 else None
        if gap < 0.9:
            return None
        return 0.8 if gap < 2.0 else 1.0

    def run(self, doc: str, duration: float, tokens: dict[str, TrackTokens], episode: str,
            progress: Progress = lambda f, s: None, cache_dir: Path | None = None,
            cancelled: Callable[[], bool] = lambda: False, extra_rules: str = "") -> FirstCutResult:
        progress(0.0, tr("规则第一刀（AI 没接上）：收紧停顿"))
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
                                "reason": tr("{p0}→{p1} {gap}s→{tgt}s（规则）", p0=self.names.get(who, who), p1=self.names.get(tag, tag),
                                              gap=f"{gap:.2f}", tgt=tgt), "confidence": 0.6})
            if end is None or e > end:
                end, who = e, tag
        progress(1.0, tr("规则第一刀完成"))
        return FirstCutResult({"episode": episode, "model": "rules (AI not connected): pause targets only",
                               "notes": tr("AI 没接上：只按学到的停顿目标收紧了停顿。"), "ops": ops},
                              {}, [tr("AI 没接上：只收紧了停顿。")])


def make_first_cut(kind: str = "auto"):
    if kind == "rules":
        return RuleFirstCut()
    c = ClaudeFirstCut()
    if kind == "claude" or c.available:
        return c
    return RuleFirstCut()
