"""Turn a playhead-anchored instruction into a proposed edit.

The adapter sees only text and numbers (positions, pause lengths, nearby edits) - never audio
- and can only *choose* among source-range operations: cut a timeline range or restore an
existing edit. It cannot write words or synthesise sound.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Protocol

from .analysis import Span

TARGET_PAUSE_S = 0.4
MAX_SENTENCE_S = 25.0


@dataclass
class ChatContext:
    instruction: str
    playhead: float                     # timeline seconds
    duration: float
    pauses: list[Span]                  # quiet runs near the playhead (timeline seconds)
    sentence: Span | None               # speech stretch containing / after the playhead
    nearby_edits: list[dict] = field(default_factory=list)   # {id, t, title, status, category}
    transcript: str = ""                # words near the playhead, if a transcript exists


@dataclass
class Proposal:
    message: str                        # reply to the user (Chinese)
    action: str = "none"                # "cut" | "restore" | "none"
    start: float | None = None          # cut: timeline seconds
    end: float | None = None
    edit_id: str | None = None          # restore: which edit
    category: str = "chat"
    title: str = ""
    reason: str = ""
    confidence: float = 0.0


class EditorAdapter(Protocol):
    name: str

    def propose(self, ctx: ChatContext) -> Proposal: ...


def _fmt(s: float) -> str:
    return f"{int(s // 60)}:{int(s % 60):02d}"


class MockEditorAdapter:
    """Deterministic rules for a few common commands. Offline, free, used in tests and demos."""

    name = "mock"

    RULES = (
        ("restore", re.compile(r"恢复|还原|撤回这处|别删|保留")),
        ("pause", re.compile(r"停顿|空白|气口|节奏.*(紧|快)")),
        ("sentence", re.compile(r"删掉?这句|删除这句|这句.*(不要|删)|去掉这句")),
    )

    def propose(self, ctx: ChatContext) -> Proposal:
        text = ctx.instruction.strip()
        for kind, rx in self.RULES:
            if rx.search(text):
                return getattr(self, f"_{kind}")(ctx)
        return Proposal("我（演示用规则引擎）目前只听得懂：「停顿短一点」「恢复这处」「删掉这句」。"
                        "接上 Claude 之后可以说更自由的话。")

    def _restore(self, ctx: ChatContext) -> Proposal:
        cands = [e for e in ctx.nearby_edits if e["status"] == "applied" and e["category"] != "loudness"]
        if not cands:
            return Proposal("这附近 20 秒内没有已应用的改动可以恢复。")
        # prefer the closest edit at or before the playhead ("前面那句"), else the closest after
        before = [e for e in cands if e["t"] <= ctx.playhead + 0.5]
        e = (max(before, key=lambda e: e["t"]) if before
             else min(cands, key=lambda e: abs(e["t"] - ctx.playhead)))
        return Proposal(f"恢复 {_fmt(e['t'])} 的「{e['title']}」，原话放回去。", action="restore",
                        edit_id=e["id"], title=f"恢复：{e['title']}",
                        reason="按你的指令恢复", confidence=1.0)

    def _pause(self, ctx: ChatContext) -> Proposal:
        long = [p for p in ctx.pauses if p.length >= TARGET_PAUSE_S + 0.3]
        if not long:
            return Proposal("附近没有明显偏长的停顿（都在 0.7 秒以内），先不动。")
        p = min(long, key=lambda p: (abs((p.start + p.end) / 2 - ctx.playhead)))
        cut = p.length - TARGET_PAUSE_S
        a = round(p.start + TARGET_PAUSE_S / 2, 3)
        return Proposal(f"把 {_fmt(p.start)} 的停顿从 {p.length:.1f} 秒收到 {TARGET_PAUSE_S} 秒。",
                        action="cut", start=a, end=round(a + cut, 3), category="pause",
                        title=f"停顿 {p.length:.1f}s → {TARGET_PAUSE_S}s",
                        reason="按你的指令收紧停顿", confidence=0.9)

    def _sentence(self, ctx: ChatContext) -> Proposal:
        s = ctx.sentence
        if s is None:
            return Proposal("没找到播放点附近的这句话。")
        if s.length > MAX_SENTENCE_S:
            return Proposal(f"这段连续说了 {s.length:.0f} 秒，太长了，不确定你说的是哪一句。"
                            "可以停在那句话开头再说一次。")
        after = [p for p in ctx.pauses if p.start >= s.end - 0.01]
        gap = after[0].length if after else 0.0
        end = s.end + max(0.0, gap - TARGET_PAUSE_S)       # take the following pause down too
        return Proposal(f"删掉 {_fmt(s.start)} 开始的这句（{s.length:.1f} 秒）。", action="cut",
                        start=round(s.start, 3), end=round(end, 3), category="content",
                        title=f"删除 {end - s.start:.1f} 秒 · 按指令删句",
                        reason="按你的指令删除这句话", confidence=0.6)


class ClaudeEditorAdapter:
    """Asks Claude (Messages API, key from ANTHROPIC_API_KEY) to choose one action.

    Only text and numeric features are sent. Not exercised by tests (no key, no network)."""

    name = "claude"
    model = "claude-opus-5-5"

    TOOL = {
        "name": "propose_edit",
        "description": "Propose exactly one non-destructive edit near the playhead, or none.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["message", "action", "start", "end", "edit_id", "title", "reason",
                         "confidence", "category"],
            "properties": {
                "message": {"type": "string", "description": "Reply to the host, Simplified Chinese."},
                "action": {"type": "string", "enum": ["cut", "restore", "none"]},
                "start": {"type": ["number", "null"], "description": "cut start, timeline seconds"},
                "end": {"type": ["number", "null"], "description": "cut end, timeline seconds"},
                "edit_id": {"type": ["string", "null"], "description": "restore: id of a nearby edit"},
                "title": {"type": "string"},
                "reason": {"type": "string"},
                "confidence": {"type": "number"},
                "category": {"type": "string", "enum": ["pause", "filler", "content", "chat"]},
            },
        },
    }

    SYSTEM = ("You are the producer of a two-host Chinese film podcast. Golden rule: preserve the "
              "conversation, polish the delivery, remove awkwardness, not personality. You can only "
              "cut a timeline range (seconds) or restore an earlier edit; you can never add or "
              "rewrite words. Place cut boundaries inside listed pauses. Answer by calling "
              "propose_edit exactly once.")

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def build_request(self, ctx: ChatContext) -> dict:
        features = {
            "instruction": ctx.instruction, "playhead_s": round(ctx.playhead, 2),
            "duration_s": round(ctx.duration, 1),
            "pauses": [[round(p.start, 2), round(p.end, 2)] for p in ctx.pauses],
            "sentence": [round(ctx.sentence.start, 2), round(ctx.sentence.end, 2)] if ctx.sentence else None,
            "nearby_edits": ctx.nearby_edits, "transcript": ctx.transcript,
        }
        return dict(model=self.model, max_tokens=4000, system=self.SYSTEM,
                    output_config={"effort": "low"},
                    tools=[self.TOOL], tool_choice={"type": "auto"},
                    messages=[{"role": "user", "content": json.dumps(features, ensure_ascii=False)}])

    def propose(self, ctx: ChatContext) -> Proposal:
        if not self.available:
            return Proposal("没有配置 ANTHROPIC_API_KEY，AI 制作人暂时不可用；可以用 --editor mock 试用规则引擎。")
        import anthropic  # optional dependency: pip install "lacuna[claude]"

        client = anthropic.Anthropic(api_key=self.api_key)
        try:
            # Server-side fallback lets a refused request be retried on another model.
            resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"],
                                               fallbacks="default", **self.build_request(ctx))
        except anthropic.APIConnectionError:
            return Proposal("连不上 Claude（网络问题），这次没有改动。")
        except anthropic.APIStatusError as e:
            return Proposal(f"Claude 返回错误（{e.status_code}），这次没有改动。")
        if resp.stop_reason == "refusal":
            return Proposal("Claude 没有处理这条指令，这次没有改动。")
        for block in resp.content:
            if block.type == "tool_use" and block.name == "propose_edit":
                return self.parse(block.input)
        return Proposal("Claude 没有给出改动建议。")

    @staticmethod
    def parse(d: dict) -> Proposal:
        p = Proposal(**{k: d.get(k) for k in asdict(Proposal("")) if k in d})
        if p.action not in ("cut", "restore", "none"):
            p.action = "none"
        if p.action == "cut" and (p.start is None or p.end is None or p.end <= p.start):
            p.action = "none"
        return p


def make_adapter(kind: str = "auto") -> EditorAdapter:
    if kind == "mock":
        return MockEditorAdapter()
    claude = ClaudeEditorAdapter()
    if kind == "claude" or (kind == "auto" and claude.available):
        return claude
    return MockEditorAdapter()
