"""Turn a playhead-anchored instruction into a proposed edit.

The adapter sees only text and numbers (transcript, positions, pause lengths, nearby edits) -
never audio - and can only *choose* among source-range operations: cut a timeline range (all
tracks or one host's track), shorten a pause, or restore an existing edit. It cannot write words
or synthesise sound. The Claude adapter refers to utterances / pauses / edits by the ids it was
shown; `resolve` turns those references into timeline ranges, so a model can never invent a time.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .analysis import Span
from .i18n import AI_NAME_RULE, in_reply_language, tr

TARGET_PAUSE_S = 0.4
MAX_SENTENCE_S = 25.0
MAX_ACTIONS = 8
JOIN_PAUSE_MAX_S = 0.5         # longest pause a sentence cut leaves where it joins


@dataclass(frozen=True)
class Word:
    text: str
    start: float                        # timeline seconds
    end: float


@dataclass
class Utterance:
    """A run of one host's words without a long gap, as it sounds on the current timeline."""
    id: str
    speaker: str
    words: list[Word]

    @property
    def start(self) -> float:
        return self.words[0].start

    @property
    def end(self) -> float:
        return self.words[-1].end

    @property
    def text(self) -> str:
        return "".join(w.text for w in self.words)


@dataclass
class ChatContext:
    instruction: str
    playhead: float                     # timeline seconds
    duration: float
    pauses: list[Span]                  # quiet runs near the playhead (timeline seconds)
    sentence: Span | None               # speech stretch containing / after the playhead
    nearby_edits: list[dict] = field(default_factory=list)   # {id, t, title, status, category, ...}
    transcript: str = ""                # words near the playhead, if a transcript exists
    utterances: list[Utterance] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)        # earlier turns {said, at, reply, outcome}


@dataclass
class Proposal:
    message: str                        # reply to the user (Chinese)
    action: str = "none"                # "cut" | "restore" | "none" (single-action adapters)
    start: float | None = None          # cut: timeline seconds
    end: float | None = None
    edit_id: str | None = None          # restore: which edit
    category: str = "chat"
    title: str = ""
    reason: str = ""
    confidence: float = 0.0
    cuts: list[dict] = field(default_factory=list)       # {start, end, track|None} timeline seconds
    restores: list[str] = field(default_factory=list)    # edit ids
    notes: list[str] = field(default_factory=list)       # warnings shown after the message
    usage: dict | None = None                            # API usage of this turn, if any

    def normalized(self) -> tuple[list[dict], list[str]]:
        """(cuts, restores) whichever way the adapter filled them in."""
        cuts = list(self.cuts)
        restores = list(self.restores)
        if self.action == "cut" and self.start is not None and self.end is not None:
            cuts.append({"start": self.start, "end": self.end, "track": None})
        if self.action == "restore" and self.edit_id:
            restores.append(self.edit_id)
        return cuts, restores


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
        return Proposal(tr("我（演示用规则引擎）目前只听得懂：「停顿短一点」「恢复这处」「删掉这句」。接上 AI 之后可以说更自由的话。"))

    def _restore(self, ctx: ChatContext) -> Proposal:
        cands = [e for e in ctx.nearby_edits if e["status"] == "applied" and e["category"] != "loudness"]
        if not cands:
            return Proposal(tr("这附近 20 秒内没有已应用的改动可以恢复。"))
        # prefer the closest edit at or before the playhead ("前面那句"), else the closest after
        before = [e for e in cands if e["t"] <= ctx.playhead + 0.5]
        e = (max(before, key=lambda e: e["t"]) if before
             else min(cands, key=lambda e: abs(e["t"] - ctx.playhead)))
        return Proposal(tr("恢复 {p0} 的「{title}」，原话放回去。", p0=_fmt(e['t']), title=e['title']), action="restore",
                        edit_id=e["id"], title=tr("恢复：{title}", title=e['title']),
                        reason=tr("按你的指令恢复"), confidence=1.0)

    def _pause(self, ctx: ChatContext) -> Proposal:
        long = [p for p in ctx.pauses if p.length >= TARGET_PAUSE_S + 0.3]
        if not long:
            return Proposal(tr("附近没有明显偏长的停顿（都在 0.7 秒以内），先不动。"))
        p = min(long, key=lambda p: (abs((p.start + p.end) / 2 - ctx.playhead)))
        cut = p.length - TARGET_PAUSE_S
        a = round(p.start + TARGET_PAUSE_S / 2, 3)
        return Proposal(tr("把 {p0} 的停顿从 {length} 秒收到 {TARGET_PAUSE_S} 秒。", p0=_fmt(p.start), length=f"{p.length:.1f}", TARGET_PAUSE_S=TARGET_PAUSE_S),
                        action="cut", start=a, end=round(a + cut, 3), category="pause",
                        title=tr("停顿 {length}s → {TARGET_PAUSE_S}s", length=f"{p.length:.1f}", TARGET_PAUSE_S=TARGET_PAUSE_S),
                        reason=tr("按你的指令收紧停顿"), confidence=0.9)

    def _sentence(self, ctx: ChatContext) -> Proposal:
        s = ctx.sentence
        if s is None:
            return Proposal(tr("没找到播放点附近的这句话。"))
        if s.length > MAX_SENTENCE_S:
            return Proposal(tr("这段连续说了 {length} 秒，太长了，不确定你说的是哪一句。可以停在那句话开头再说一次。", length=f"{s.length:.0f}"))
        after = [p for p in ctx.pauses if p.start >= s.end - 0.01]
        gap = after[0].length if after else 0.0
        end = s.end + max(0.0, gap - TARGET_PAUSE_S)       # take the following pause down too
        return Proposal(tr("删掉 {p0} 开始的这句（{length} 秒）。", p0=_fmt(s.start), length=f"{s.length:.1f}"), action="cut",
                        start=round(s.start, 3), end=round(end, 3), category="content",
                        title=tr("删除 {p0} 秒 · 按指令删句", p0=f"{end - s.start:.1f}"),
                        reason=tr("按你的指令删除这句话"), confidence=0.6)


# ---------------------------------------------------------------------------- Claude

def find_api_key() -> tuple[str | None, str]:
    """(key, where it came from). Never log the key itself.

    On Windows a key saved with `setx` / System Properties is only in the environment of
    processes started *after* it was saved; a server started from an older shell (or a remote
    session) would not see it, so fall back to the user / machine environment in the registry."""
    key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip().strip('"')
    if key:
        return key, "env"
    if sys.platform == "win32":
        found = _windows_registry_key()
        if found:
            return found
    if sys.platform == "darwin":
        found = _macos_keychain_key()
        if found:
            return found
    found = _file_key()
    if found:
        return found
    return None, "missing"


# Where the 设置 page saves a key (phase 7): Windows = the user environment in the registry (what
# `setx` writes, read above); macOS = the login Keychain (a Mac app started from the Dock gets no
# shell environment); elsewhere = a 0600 file in the install root.
KEYCHAIN_SERVICE = "LACUNA"
KEYCHAIN_ACCOUNT = "ANTHROPIC_API_KEY"


def _macos_keychain_key() -> tuple[str, str] | None:
    try:
        out = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT, "-w"],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    v = out.stdout.strip()
    return (v, "keychain") if out.returncode == 0 and v else None


def _key_file() -> Path:
    home = os.environ.get("LACUNA_HOME")
    return (Path(home) if home else Path.home() / ".config" / "lacuna") / "api_key"


def _file_key() -> tuple[str, str] | None:
    try:
        v = _key_file().read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return (v, "file") if v else None


def save_api_key(key: str) -> str:
    """Store the key where `find_api_key` looks for it on this OS; returns where. Never logs it."""
    key = key.strip().strip('"')
    if len(key) < 20 or any(c.isspace() for c in key):
        raise ValueError(tr("这不像一个 AI 密钥（应该是 sk- 开头的一长串）"))
    if sys.platform == "win32":
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, "ANTHROPIC_API_KEY", 0, winreg.REG_SZ, key)
        where = "registry-user"
    elif sys.platform == "darwin":
        out = subprocess.run(["security", "add-generic-password", "-U", "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT,
                              "-w", key], capture_output=True, text=True, timeout=20)
        if out.returncode != 0:
            raise OSError(tr("存进钥匙串失败：{p0}", p0=out.stderr.strip()))
        where = "keychain"
    else:
        f = _key_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(key)
        where = "file"
    # this process (and what it starts) sees it at once; a running Claude client is made at startup
    os.environ.pop("ANTHROPIC_API_KEY", None)
    return where


def _windows_registry_key() -> tuple[str, str] | None:
    import winreg
    for root, path, where in (
            (winreg.HKEY_CURRENT_USER, "Environment", "registry-user"),
            (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
             "registry-machine")):
        try:
            with winreg.OpenKey(root, path) as k:
                v, _ = winreg.QueryValueEx(k, "ANTHROPIC_API_KEY")
        except OSError:
            continue
        v = str(v or "").strip().strip('"')
        if v:
            return v, where
    return None


def sdk_installed() -> bool:
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


# USD per million tokens (input, output); unknown models are priced like Opus 5.
PRICES = {"claude-opus-5-5": (4.0, 20.0), "claude-opus-5": (5.0, 25.0), "claude-sonnet-5-5": (2.0, 10.0)}

SYSTEM = """\
You are the AI producer inside LACUNA Studio, editing 《洛城二三事》, a casual two-host Chinese \
film podcast (hosts: Leon and Pei, one track each). The host is listening to the current cut, \
paused at a playhead, and tells you what to change there. Reply in Simplified Chinese.

Golden rule: preserve the conversation, polish the delivery; remove awkwardness, not personality.
- You can only remove recorded audio or bring back audio an earlier edit removed. You can never \
add, reorder or rewrite words. Never suggest re-recording or adding music in this chat.
- Be strict with Leon's rambling, repeated explanations, false starts and off-point detail; be \
somewhat strict with Pei's clear stumbles, but gentler than with Leon.
- Keep some natural fillers / verbal tics; too clean sounds fake. Natural repetition for emphasis \
is not an error. Pauses between turns sound right at about 0.4 s.
- When it is unclear what the host means (which sentence, how much), do nothing and ask one short \
question instead of guessing.

What you are given (JSON): the instruction, the playhead (timeline seconds), the utterances \
around it as they sound now (id, speaker, start/end seconds, text), the silent pauses (id, length), \
nearby edits (id, status "applied" = audio removed now / "restored" = original audio is back, \
what they removed), and the last few turns of this chat. "这句 / 这里" \
means the utterance at or just before the playhead; "刚才 / 前面那句" usually means earlier.

Answer by calling propose_edit exactly once. Actions:
- cut: remove from from_utterance through to_utterance on both tracks (the timeline closes up). \
To remove only part of an utterance, give start_text (the first words removed, copied exactly \
from that utterance's text) and/or end_text (the last words removed, copied exactly from \
to_utterance's text).
- cut_one_track: same selection, but only that speaker's sound is erased (filled with their own \
room tone, so no hole is heard) and nothing moves; use it for one host's interjection, 嗯 / 对 \
backchannel or noise over the other host's speech ("抹掉 Pei 那几个嗯"): one action per utterance.
- shorten_pause: shorten pause `pause` to target_s seconds (default 0.4).
- restore: undo nearby edit `edit` so the original audio comes back.
Use an empty actions list when nothing should change. The host previews every proposal before \
it is applied. `message` says in one or two short sentences what will change and where (m:ss); \
`title` is a short label of the change; confidence is how sure you are this is what the host wants.""" + AI_NAME_RULE  # i18n-ignore

_ID = {"type": ["string", "null"]}
TOOL = {
    "name": "propose_edit",
    "description": "Propose one change near the playhead (possibly several actions), or none.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["message", "title", "reason", "confidence", "category", "actions"],
        "properties": {
            "message": {"type": "string", "description": "Reply to the host, Simplified Chinese."},
            "title": {"type": "string", "description": "Short label, Simplified Chinese."},
            "reason": {"type": "string", "description": "Why, one sentence, Simplified Chinese."},
            "confidence": {"type": "number"},
            "category": {"type": "string", "enum": ["pause", "filler", "content", "interjection", "chat"]},
            "actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["type", "from_utterance", "to_utterance", "start_text", "end_text",
                                 "pause", "target_s", "edit"],
                    "properties": {
                        "type": {"type": "string", "enum": ["cut", "cut_one_track", "shorten_pause", "restore"]},
                        "from_utterance": _ID | {"description": "cut: first utterance id"},
                        "to_utterance": _ID | {"description": "cut: last utterance id (null = same)"},
                        "start_text": _ID | {"description": "cut: first removed words, verbatim"},
                        "end_text": _ID | {"description": "cut: last removed words, verbatim"},
                        "pause": _ID | {"description": "shorten_pause: pause id"},
                        "target_s": {"type": ["number", "null"], "description": "shorten_pause: seconds to keep"},
                        "edit": _ID | {"description": "restore: edit id"},
                    },
                },
            },
        },
    },
}


def scene(ctx: ChatContext) -> dict:
    """Everything the model sees: text and numbers only."""
    r = lambda x: round(x, 2)  # noqa: E731
    at = next((u.id for u in ctx.utterances if u.start <= ctx.playhead < u.end + 0.3), None)
    if at is None:
        before = [u for u in ctx.utterances if u.start <= ctx.playhead]
        at = before[-1].id if before else (ctx.utterances[0].id if ctx.utterances else None)
    return {
        "instruction": ctx.instruction,
        "playhead": r(ctx.playhead), "playhead_mmss": _fmt(ctx.playhead), "playhead_utterance": at,
        "episode_length": r(ctx.duration),
        "utterances": [{"id": u.id, "speaker": u.speaker, "start": r(u.start), "end": r(u.end), "text": u.text}
                       for u in ctx.utterances],
        "pauses": [{"id": f"p{i + 1}", "start": r(p.start), "end": r(p.end), "length": r(p.length)}
                   for i, p in enumerate(ctx.pauses)],
        "nearby_edits": [{"id": e["id"], "at": e.get("t"), "removed_s": e.get("len"), "status": e.get("status"),
                          "kind": e.get("category"), "title": e.get("title"), "source": e.get("source"),
                          "removed_text": e.get("removed_text", "")} for e in ctx.nearby_edits],
        "recent_turns": ctx.history,
    }


class ClaudeEditorAdapter:
    """Asks Claude (Messages API, key from ANTHROPIC_API_KEY) to choose the change.

    Only text and numeric features are sent. `client` can be injected (tests use a fake)."""

    name = "claude"
    model = "claude-opus-5-5"

    def __init__(self, api_key: str | None = None, client: Any = None, effort: str | None = None):
        if api_key is None and client is None:
            api_key, self.key_source = find_api_key()
        else:
            self.key_source = "given"
        self.api_key = api_key
        self._client = client
        self.effort = effort or os.environ.get("LACUNA_AI_EFFORT", "low")

    @property
    def available(self) -> bool:
        return self._client is not None or (bool(self.api_key) and sdk_installed())

    @property
    def client(self):
        if self._client is None:
            import anthropic  # optional dependency: pip install "lacuna[claude]"
            self._client = anthropic.Anthropic(api_key=self.api_key, timeout=90.0, max_retries=1)
        return self._client

    def build_request(self, ctx: ChatContext) -> dict:
        return dict(model=self.model, max_tokens=8000, system=in_reply_language(SYSTEM),
                    output_config={"effort": self.effort},
                    tools=[in_reply_language(TOOL)], tool_choice={"type": "auto"},
                    messages=[{"role": "user", "content": json.dumps(scene(ctx), ensure_ascii=False)}])

    def propose(self, ctx: ChatContext) -> Proposal:
        if not self.available:
            return Proposal(tr("还没接上 AI（没有 AI 密钥），AI 制作人暂时不可用。"))
        t0 = time.monotonic()
        try:
            resp = self._call(ctx)
        except Exception as e:      # noqa: BLE001 - every failure becomes a no-change reply
            return Proposal(error_message(e))
        usage = self._usage(resp, time.monotonic() - t0)
        if resp.stop_reason == "refusal":
            p = Proposal(tr("LACUNA 没有处理这条指令，这次没有改动。"))
        else:
            p = None
            for block in resp.content:
                if block.type == "tool_use" and block.name == "propose_edit":
                    p = resolve(block.input, ctx)
                    break
            if p is None:
                text = "".join(b.text for b in resp.content if b.type == "text").strip()
                p = Proposal(text or (tr("回答被截断了，这次没有改动。") if resp.stop_reason == "max_tokens"
                                      else tr("LACUNA 没有给出改动建议。")))
        p.usage = usage
        return p

    def _call(self, ctx: ChatContext):
        # Server-side fallback lets a refused request be retried on another model.
        return self.client.beta.messages.create(betas=["server-side-fallback-2026-07-01"],
                                                fallbacks="default", **self.build_request(ctx))

    @staticmethod
    def _usage(resp, seconds: float) -> dict:
        u = getattr(resp, "usage", None)
        tin = (getattr(u, "input_tokens", 0) or 0) + (getattr(u, "cache_creation_input_tokens", 0) or 0)
        cached = getattr(u, "cache_read_input_tokens", 0) or 0
        tout = getattr(u, "output_tokens", 0) or 0
        model = getattr(resp, "model", None) or ClaudeEditorAdapter.model
        pin, pout = PRICES.get(model, (5.0, 25.0))
        cost = (tin * pin + cached * pin * 0.1 + tout * pout) / 1e6
        return {"model": model, "input_tokens": tin + cached, "output_tokens": tout,
                "seconds": round(seconds, 2), "cost_usd": round(cost, 4),
                "request_id": getattr(resp, "_request_id", None)}


def error_message(e: Exception, tail: str | None = None) -> str:
    """A short explanation of an API failure, in the interface language. `tail` defaults to
    "nothing was changed"; pass "" to leave it off or another sentence to replace it."""
    try:
        import anthropic
    except ImportError:
        anthropic = None
    tail = tr("，这次没有改动。") if tail is None else tail
    if anthropic is None:
        return tr("调用 AI 服务失败（{name}）", name=type(e).__name__) + tail
    if isinstance(e, anthropic.APITimeoutError):
        return tr("AI 服务太久没有回应（超时）") + tail
    if isinstance(e, anthropic.APIConnectionError):
        return tr("连不上 AI 服务（网络问题）") + tail
    if isinstance(e, anthropic.AuthenticationError):
        return tr("API key 无效或已被撤销（401），请在 Console 检查 key") + tail
    if isinstance(e, anthropic.PermissionDeniedError):
        return tr("这个 API key 没有调用权限（403）") + tail
    if isinstance(e, anthropic.RateLimitError):
        return tr("请求太频繁，被限流了（429），等一会儿再说") + tail
    if isinstance(e, anthropic.APIStatusError):
        msg = str(getattr(e, "message", "") or e).lower()
        if "credit" in msg or "billing" in msg or "balance" in msg:
            return tr("API 额度用完了（或账单未开通），请在 Console 的 Billing 查看") + tail
        if e.status_code in (500, 502, 503, 504, 529):
            return tr("AI 服务暂时繁忙（{status_code}），稍后再试", status_code=e.status_code) + tail
        return tr("AI 服务返回错误（{status_code}）", status_code=e.status_code) + tail
    return tr("调用 AI 服务失败（{name}）", name=type(e).__name__) + tail


# ---------------------------------------------------------------------------- resolving ids

_PUNCT = re.compile(r"[\s，。、！？,.!?…\"'“”‘’：:；;（）()《》<>\-—~～]")


def _norm(s: str) -> str:
    return _PUNCT.sub("", s or "").lower()


def _locate(u: Utterance, quote: str, after: int = 0) -> tuple[int, int] | None:
    """Word indices (first, last) of the first verbatim occurrence of `quote` in `u` at or
    after word `after`, ignoring spaces and punctuation."""
    chars, owner = [], []
    for wi, w in enumerate(u.words):
        for ch in _norm(w.text):
            chars.append(ch)
            owner.append(wi)
    q = _norm(quote)
    if not q:
        return None
    first = next((i for i, o in enumerate(owner) if o >= after), len(owner))
    idx = "".join(chars).find(q, first)
    if idx < 0:
        return None
    return owner[idx], owner[idx + len(q) - 1]


class _Unresolved(ValueError):
    pass


def _select(a: dict, utts: dict[str, Utterance]) -> tuple[Utterance, int, Utterance, int]:
    u1 = utts.get(a.get("from_utterance") or "")
    if u1 is None:
        raise _Unresolved(tr("没有片段 {p0}", p0=a.get('from_utterance')))
    u2 = utts.get(a.get("to_utterance") or "") or u1
    if u2.start < u1.start:
        u1, u2 = u2, u1
    i1, j2 = 0, len(u2.words) - 1
    if a.get("start_text"):
        loc = _locate(u1, a["start_text"])
        if loc is None:
            raise _Unresolved(tr("在 {id} 里找不到「{start_text}」", id=u1.id, start_text=a['start_text']))
        i1 = loc[0]
    if a.get("end_text"):
        loc = _locate(u2, a["end_text"], after=i1 if u2 is u1 else 0)
        if loc is None:
            raise _Unresolved(tr("在 {id} 里找不到「{end_text}」", id=u2.id, end_text=a['end_text']))
        j2 = loc[1]
    if u1 is u2 and j2 < i1:
        raise _Unresolved(tr("起止文字顺序反了"))
    return u1, i1, u2, j2


def _range_cut(a: dict, ctx: ChatContext, utts: dict[str, Utterance]) -> tuple[dict, str | None]:
    u1, i1, u2, j2 = _select(a, utts)
    start, end = u1.words[i1].start, u2.words[j2].end
    allw = [(u.speaker, w) for u in ctx.utterances for w in u.words]
    prev_end = max((w.end for _, w in allw if w.start < start and w.end <= start + 0.01), default=None)
    next_start = min((w.start for _, w in allw if w.end > end and w.start >= end - 0.01), default=None)
    gb = max(0.0, start - prev_end) if prev_end is not None else 0.0
    ga = max(0.0, next_start - end) if next_start is not None else 0.0
    # leave one natural pause where the two sides join: the longer of the two, at most 0.5 s
    desired = min(max(gb, ga), JOIN_PAUSE_MAX_S)
    keep_after = min(max(desired - gb, 0.0), ga)
    x_after = ga - keep_after
    x_before = max(0.0, gb + keep_after - desired)
    cut = {"start": round(start - x_before, 3), "end": round(end + x_after, 3), "track": None}
    speakers = {u1.speaker, u2.speaker}
    caught = "".join(w.text for sp, w in allw if sp not in speakers
                     and cut["start"] <= (w.start + w.end) / 2 < cut["end"])
    note = None
    if caught:
        other = next(sp for sp, _ in allw if sp not in speakers)
        note = tr("注意：这段里 {other} 也有「{words}」会一起删掉。", other=other, words=caught[:16] + ('…' if len(caught) > 16 else ''))
    return cut, note


def _track_cut(a: dict, ctx: ChatContext, utts: dict[str, Utterance]) -> dict:
    u1, i1, u2, j2 = _select(a, utts)
    if u1.speaker != u2.speaker:
        raise _Unresolved(tr("单轨删除只能选同一个人的话"))
    start, end = u1.words[i1].start, u2.words[j2].end
    return {"start": round(max(0.0, start - 0.03), 3), "end": round(end + 0.03, 3), "track": u1.speaker}


def resolve(d: dict, ctx: ChatContext) -> Proposal:
    """Model output (ids + verbatim quotes) -> Proposal with timeline ranges. Anything that does
    not match what the model was shown is dropped with a note."""
    p = Proposal(str(d.get("message") or ""), category=d.get("category") or "chat",
                 title=str(d.get("title") or ""), reason=str(d.get("reason") or ""))
    try:
        p.confidence = max(0.0, min(1.0, float(d.get("confidence") or 0.0)))
    except (TypeError, ValueError):
        p.confidence = 0.0
    if p.category not in ("pause", "filler", "content", "interjection", "chat"):
        p.category = "chat"
    actions = [a for a in (d.get("actions") or []) if isinstance(a, dict)]
    if len(actions) > MAX_ACTIONS:
        p.notes.append(tr("一次最多 {MAX_ACTIONS} 处，后面的先不动。", MAX_ACTIONS=MAX_ACTIONS))
        actions = actions[:MAX_ACTIONS]
    utts = {u.id: u for u in ctx.utterances}
    edits = {e["id"]: e for e in ctx.nearby_edits}
    failed = 0
    for a in actions:
        kind = a.get("type")
        try:
            if kind == "cut":
                cut, note = _range_cut(a, ctx, utts)
                p.cuts.append(cut)
                if note:
                    p.notes.append(note)
            elif kind == "cut_one_track":
                p.cuts.append(_track_cut(a, ctx, utts))
            elif kind == "shorten_pause":
                m = re.fullmatch(r"p(\d+)", str(a.get("pause") or ""))
                if not m or not 1 <= int(m.group(1)) <= len(ctx.pauses):
                    raise _Unresolved(tr("没有停顿 {p0}", p0=a.get('pause')))
                sp = ctx.pauses[int(m.group(1)) - 1]
                target = a.get("target_s")
                target = TARGET_PAUSE_S if target is None else max(0.15, min(2.0, float(target)))
                if sp.length - target < 0.1:
                    raise _Unresolved(tr("{p0} 的停顿只有 {length} 秒，已经够短", p0=_fmt(sp.start), length=f"{sp.length:.1f}"))
                p.cuts.append({"start": round(sp.start + target / 2, 3), "end": round(sp.end - target / 2, 3),
                               "track": None})
            elif kind == "restore":
                e = edits.get(a.get("edit") or "")
                if e is None:
                    raise _Unresolved(tr("附近没有改动 {p0}", p0=a.get('edit')))
                if e.get("status") != "applied":
                    raise _Unresolved(tr("「{p0}」已经是原话了", p0=e.get('title')))
                if e["id"] not in p.restores:
                    p.restores.append(e["id"])
            else:
                raise _Unresolved(tr("不认识的动作 {kind}", kind=kind))
        except (_Unresolved, TypeError, ValueError) as err:
            failed += 1
            p.notes.append(tr("有一处没对上（{err}），没有采用。", err=err))
    if actions and failed == len(actions):
        p.notes.append(tr("这次没有改动，可以换个说法再试。"))
    if not p.message:
        p.message = tr("好的。") if (p.cuts or p.restores) else tr("这次没有改动。")
    return p


def editor_status(adapter: EditorAdapter) -> dict:
    """What the UI shows about the AI producer: which engine, and if not Claude, why."""
    if adapter.name == "claude":
        return {"editor": "claude", "editor_note": ""}
    key, _ = find_api_key()
    if key and not sdk_installed():
        note = tr("找到了 AI 密钥，但 AI 组件没装好（请重新安装 LACUNA）")
    elif not key:
        note = tr("没找到 AI 密钥")
    else:
        note = tr("以演示规则启动（--editor mock）")
    return {"editor": adapter.name, "editor_note": note}


def make_adapter(kind: str = "auto") -> EditorAdapter:
    if kind == "mock":
        return MockEditorAdapter()
    claude = ClaudeEditorAdapter()
    if kind == "claude" or (kind == "auto" and claude.available):
        return claude
    return MockEditorAdapter()
