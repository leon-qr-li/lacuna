"""Long-term asks from the AI producer chat (phase 5 follow-up): what Leon *says* becomes candidate rules.

Review outcomes (``learning.py``) only see what happened to edits. Leon also states standing wishes in
the chat ("以后 Pei 的嗯都别删"); those are learned here, two ways:

* ``记住：……`` / ``remember: ...`` in the chat -> one candidate rule at once, in his own words, no AI call.
* After an export, one small Claude call reads that episode's chat log (``<episode>/chat.json``: what he
  said, the producer's reply, whether he approved) and picks out the asks meant for every episode, not
  just the spot he was at. Only text goes to the API. Each ask keeps the sentences it came from.

Both land as ``kind="ask"`` rules on the 学到的规则 page; like every learned rule they change nothing until
Leon clicks 采用 (D17), then feed the next first cut through ``learning.prompt_rules``.

Storage (D42): ``<workspace>/learning/asks/<episode>.json`` through ``store`` (atomic write + .bak),
one file per episode. An ask summarised again in a later episode reuses the earlier id, so its quotes
add up under one rule.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Callable

from .editor import ClaudeEditorAdapter, find_api_key, sdk_installed
from .i18n import AI_NAME_RULE, in_reply_language, join_list, tr
from .learning import LEARN_DIR, Rule
from .store import Workspace, atomic_write_json, check_id, read_json

ASKS_DIR = "asks"
REMEMBER = re.compile(r"^\s*(?:帮我记住|记住|记一下|remember)\s*[:：,，]?\s*(?P<ask>[^\s:：,，].{3,})$", re.I | re.S)
MAX_TURNS = 300          # most recent turns sent to the summariser
MAX_ASK = 300            # characters kept of one ask

_STR = {"type": "string"}
TOOL = {
    "name": "submit_long_term_asks",
    "description": "Submit the host's standing editing preferences found in the chat log (may be empty).",
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["asks"],
        "properties": {"asks": {"type": "array", "items": {
            "type": "object",
            "additionalProperties": False,
            "required": ["title", "instruction", "turns", "same_as"],
            "properties": {
                "title": _STR,          # Chinese, one line, for Leon
                "instruction": _STR,    # English, for the first-cut editor
                "turns": {"type": "array", "items": {"type": "integer"}},
                "same_as": _STR,        # id of an existing ask this repeats, or ""
            }}}},
    },
}

SYSTEM = """\
You read the chat log between Leon (host of 《洛城二三事》, a two-host Chinese film podcast with Pei) \
and the AI producer that edits the episode with him. Most of what he says is about one spot \
("删掉这句", "这里停顿太长"). Find only the STANDING preferences: things he wants done the same way in \
every episode, said outright ("以后…", "每次…", "Pei 的嗯都别删", "我讲题外话一律剪狠点") or clearly \
implied by the same correction made several times. A one-off instruction is not a standing preference.

For each preference return:
- title: one short line in Simplified Chinese, in Leon's voice, e.g. "Pei 的语气词「嗯」不要删".
- instruction: one sentence in English telling an AI first-cut editor what to do differently.
- turns: the numbers of the turns it comes from.
- same_as: the id of an EXISTING preference (listed in the input) that says the same thing, else "".
Do not repeat an existing preference as new. Return an empty list when there is none; that is common.""" + AI_NAME_RULE  # i18n-ignore


def _now() -> str:      # microseconds: the latest wording of an ask is picked by this
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _id(text: str) -> str:
    norm = re.sub(r"[\s，。,.!！?？：:；;「」\"'“”]+", "", text.lower())
    return hashlib.sha1(norm.encode()).hexdigest()[:10]


def remember_text(text: str) -> str | None:
    """The ask in a "记住：……" message, or None if the message is not one."""
    m = REMEMBER.match(text or "")
    return m.group("ask").strip()[:MAX_ASK] if m else None


def _mmss(s: float) -> str:
    s = int(s)
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


class ChatAsks:
    """The workspace store of asks, and how they read as rules."""

    def __init__(self, ws: Workspace):
        self.ws = ws
        self.dir = ws.root / LEARN_DIR / ASKS_DIR
        self.lock = threading.Lock()

    def _path(self, episode_id: str):
        return self.dir / f"{check_id(episode_id)}.json"

    def load(self, episode_id: str) -> dict:
        p = self._path(episode_id)
        if not p.exists() and not p.with_name(p.name + ".bak").exists():
            return {"schema": 1, "episode": episode_id, "summarized": 0, "asks": []}
        return read_json(p)

    def _save(self, episode_id: str, doc: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self._path(episode_id), doc)

    def all(self) -> list[dict]:
        out: list[dict] = []
        if self.dir.is_dir():
            for p in sorted(self.dir.glob("*.json")):
                try:
                    doc = read_json(p)
                    out += [a | {"episode": doc.get("episode", p.stem)} for a in doc.get("asks", [])]
                except (OSError, ValueError, AttributeError, TypeError):
                    continue        # one unreadable file must not hide the rest
        return out

    # ---- "记住：……"
    def remember(self, episode_id: str, text: str, at: float) -> dict:
        ask = {"id": _id(text), "title": text, "source": "remember", "at": _now(),
               "instruction": f'Leon asked the editor to remember, as a standing rule: "{text}"',
               "quotes": [{"said": f"记住：{text}", "at": round(at, 2)}]}  # i18n-ignore
        with self.lock:
            doc = self.load(episode_id)
            doc["asks"] = [a for a in doc["asks"] if a["id"] != ask["id"]] + [ask]
            self._save(episode_id, doc)
        return ask

    # ---- after export
    def pending_turns(self, episode_id: str, log: list[dict]) -> list[dict]:
        """Turns not yet summarised (a re-export after more chat only looks at the new ones)."""
        done = self.load(episode_id).get("summarized", 0)
        return log[done:] if done <= len(log) else log

    def add_summary(self, episode_id: str, found: list[dict], log: list[dict], first: int) -> list[dict]:
        """Store what the summariser found; `first` is the log index of turn 1 it was shown."""
        known = {a["id"] for a in self.all()}
        new = []
        for f in found:
            title = str(f.get("title") or "").strip()[:MAX_ASK]
            instr = str(f.get("instruction") or "").strip()[:600]
            if not title or not instr:
                continue
            quotes = []
            for n in f.get("turns") or []:
                i = first + int(n) - 1
                if first <= i < len(log) and not log[i].get("remember"):
                    quotes.append({"said": log[i]["said"][:MAX_ASK], "at": log[i].get("at", 0.0)})
            if not quotes:
                continue            # every ask must point at what he actually said
            same = str(f.get("same_as") or "")
            new.append({"id": same if same in known else _id(title), "title": title, "instruction": instr,
                        "source": "summary", "at": _now(), "quotes": quotes[:6]})
        with self.lock:
            doc = self.load(episode_id)
            ids = {a["id"] for a in new}
            doc["asks"] = [a for a in doc["asks"] if a["id"] not in ids] + new
            doc["summarized"] = len(log)
            doc["summarized_at"] = _now()
            self._save(episode_id, doc)
        return new

    # ---- as rules
    def rules(self) -> list[Rule]:
        by: dict[str, list[dict]] = {}
        for a in self.all():
            by.setdefault(a["id"], []).append(a)
        out = []
        for aid, group in by.items():
            group.sort(key=lambda a: a.get("at", ""))
            last = group[-1]                       # the latest wording wins; quotes add up
            eps = sorted({a["episode"] for a in group})
            examples = [{"text": q["said"], "raw": None, "verdict": "said", "episode": a["episode"],
                         "reason": _mmss(q.get("at", 0.0))} for a in group for q in a.get("quotes", [])]
            n = len(examples)
            how = tr("你用「记住」说的") if any(a.get("source") == "remember" for a in group) else tr("导出后从对话里总结出的")
            out.append(Rule(
                f"ask:{aid}", "ask", last["title"],
                tr("{how}，出自 {episodes} 的对话（{n} 句）。采用后从下一期的 AI 初剪开始照做。",
                   how=how, episodes=join_list(eps), n=n),
                f"Leon's standing request (from the chat): {last['instruction']}",
                {"ask": aid}, {"said": n, "episodes": eps}, examples[:6]))
        return out


# ============================================================================ the summariser

class ClaudeAskSummarizer:
    """One small request per export; `client` can be injected (tests use a fake)."""

    name = "claude"
    model = "claude-sonnet-5-5"

    def __init__(self, api_key: str | None = None, client: Any = None):
        if api_key is None and client is None:
            api_key, _ = find_api_key()
        self.api_key = api_key
        self._client = client

    @property
    def available(self) -> bool:
        return self._client is not None or (bool(self.api_key) and sdk_installed())

    @property
    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key, timeout=120.0, max_retries=1)
        return self._client

    @staticmethod
    def user_message(turns: list[dict], existing: list[dict]) -> str:
        return json.dumps({
            "existing_preferences": [{"id": a["id"], "title": a["title"]} for a in existing],
            "chat": [{"turn": i + 1, "leon_said": t["said"], "producer_replied": t.get("reply", "")[:300],
                      "outcome": {"approved": "change approved", "discarded": "change rejected"}.get(
                          t.get("state", ""), "proposed, not decided" if t.get("proposal") else "no change")}
                     for i, t in enumerate(turns)],
        }, ensure_ascii=False)

    def request(self, turns: list[dict], existing: list[dict]) -> dict:
        return dict(model=self.model, max_tokens=4000, system=in_reply_language(SYSTEM), tools=[in_reply_language(TOOL)],
                    tool_choice={"type": "tool", "name": TOOL["name"]},
                    messages=[{"role": "user", "content": self.user_message(turns, existing)}])

    def summarize(self, turns: list[dict], existing: list[dict]) -> tuple[list[dict], dict]:
        t0 = time.monotonic()
        resp = self.client.messages.create(**self.request(turns, existing))
        usage = ClaudeEditorAdapter._usage(resp, time.monotonic() - t0)
        for block in resp.content:
            if block.type == "tool_use" and block.name == TOOL["name"]:
                return list(block.input.get("asks") or []), usage
        return [], usage


class ChatLearner:
    """Runs the summariser after an export, in the background; never blocks or fails the export."""

    def __init__(self, ws: Workspace, factory: Callable[[], Any] = ClaudeAskSummarizer,
                 log_usage: Callable[[str, dict], None] = lambda e, u: None):
        self.asks = ChatAsks(ws)
        self.factory = factory
        self.log_usage = log_usage
        self.last: dict[str, dict] = {}        # episode -> outcome of the last run (for tests / the page)

    def after_export(self, ep, wait: bool = False) -> None:
        if wait:
            self.summarize(ep)
        else:
            threading.Thread(target=self.summarize, args=(ep,), name=f"chat-learn-{ep.id}", daemon=True).start()

    def summarize(self, ep) -> list[dict]:
        if ep.meta.get("demo"):
            return []
        log = ep.chat_log()
        turns = self.asks.pending_turns(ep.id, log)
        said = [t for t in turns if not t.get("remember")]
        if not said:
            self.last[ep.id] = {"state": "nothing", "new": 0}
            return []
        summarizer = self.factory()
        if not getattr(summarizer, "available", True):
            self.last[ep.id] = {"state": "no_key", "new": 0}
            return []                          # turns stay pending; the next export with a key reads them
        shown = turns[-MAX_TURNS:]
        try:
            found, usage = summarizer.summarize(shown, self.asks.all())
        except Exception:                      # noqa: BLE001 - learning must never break an export
            traceback.print_exc()
            self.last[ep.id] = {"state": "error", "new": 0}
            return []
        if usage:
            self.log_usage(ep.id, usage | {"purpose": "chat_learning"})
        new = self.asks.add_summary(ep.id, found, log, len(log) - len(shown))
        self.last[ep.id] = {"state": "done", "new": len(new)}
        return new


__all__ = ["ChatAsks", "ChatLearner", "ClaudeAskSummarizer", "remember_text"]
