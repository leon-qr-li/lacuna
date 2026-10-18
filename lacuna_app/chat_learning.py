"""Long-term asks from the AI producer chat (phase 5 follow-up): what Leon *says* becomes rules.

Review outcomes (``learning.py``) only see what happened to edits. Leon also states standing wishes in
the chat ("以后 Pei 的嗯都别删"). Since 2026-10-18 none of them is stored before he confirms how LACUNA
read it (``lessons.py``: 「记住」 drafts in the chat, the 本集学到的规则 step); this module is the store of
the confirmed ones, ``kind="ask"`` rules on the 学到的规则 page that feed the next first cut through
``learning.prompt_rules``. Asks from the old silent after-export summary (source ``summary``) stay as they are.

Storage (D42): ``<workspace>/learning/asks/<episode>.json`` through ``store`` (atomic write + .bak),
one file per episode. An ask confirmed again in a later episode reuses the earlier id, so its quotes
add up under one rule.
"""
from __future__ import annotations

import hashlib
import re
import threading
from datetime import datetime, timezone

from .i18n import join_list, tr
from .learning import LEARN_DIR, Rule
from .store import Workspace, atomic_write_json, check_id, read_json

ASKS_DIR = "asks"
REMEMBER = re.compile(r"^\s*(?:帮我记住|记住|记一下|remember)\s*[:：,，]?\s*(?P<ask>[^\s:：,，].{3,})$", re.I | re.S)
MAX_ASK = 300            # characters kept of one ask


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

    def put(self, episode_id: str, ask: dict) -> dict:
        """Store one confirmed ask (its id may be an earlier ask's: the wording is then replaced, the
        quotes add up). Called by lessons.py once Leon confirmed the rule."""
        ask = ask | {"at": _now()}
        with self.lock:
            doc = self.load(episode_id)
            before = [q for a in doc["asks"] if a["id"] == ask["id"] for q in a.get("quotes", [])]
            ask["quotes"] = (before + [q for q in ask.get("quotes", []) if q not in before])[-12:]
            doc["asks"] = [a for a in doc["asks"] if a["id"] != ask["id"]] + [ask]
            self._save(episode_id, doc)
        return ask

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
            sources = {a.get("source") for a in group}
            how = (tr("你用「记住」说的") if "remember" in sources else
                   tr("你在「本集学到的规则」里确认的") if "lesson" in sources else tr("导出后从对话里总结出的"))
            out.append(Rule(
                f"ask:{aid}", "ask", last["title"],
                tr("{how}，出自 {episodes} 的对话（{n} 句）。采用后从下一期的 AI 初剪开始照做。",
                   how=how, episodes=join_list(eps), n=n),
                f"Leon's standing request (from the chat): {last['instruction']}",
                {"ask": aid}, {"said": n, "episodes": eps}, examples[:6]))
        return out


__all__ = ["ChatAsks", "remember_text"]
