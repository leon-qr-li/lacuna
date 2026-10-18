"""Confirmed learning (首次检测 #9, #12): nothing Leon says becomes a rule until he confirms how LACUNA read it.

Two ways in, both shown to him before anything is stored as a rule:

* 「记住」 (button, or a chat message starting 记住：…): one AI call rewrites what he said into a rule and
  says how it understood it. The chat shows that draft with 记住这条 / 改一下 / 不用; 改一下 sends his
  correction back for another rewrite. Only 记住这条 stores it, and then it is in force at once (he has just
  confirmed it), on 学到的规则 as kind ``ask``. His own sentence is kept as the evidence, never as the rule.
* 本集学到的规则, a step between 整集试听 and 配乐: one AI call reads the episode's chat log and his review
  decisions and proposes the habits this episode teaches, each with its evidence and whether it is new,
  reinforces an existing rule or conflicts with one. He adopts, edits (by hand or by telling LACUNA), or
  skips each; the step can be skipped. This replaces the silent after-export summary (D: 2026-10-18).

Habits are never deleted here (Leon 2026-10-17): skipped lessons and dropped drafts stay in the file;
withdrawing a rule happens only on 学到的规则. Only text goes to the API.

Storage: ``<workspace>/learning/lessons/<episode>.json`` (atomic write + .bak), so it outlives the episode.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import traceback
from typing import Any, Callable

from .chat_learning import MAX_ASK, ChatAsks, _id as ask_id
from .ai_tools import call_tool
from .editor import ClaudeEditorAdapter, error_message, find_api_key, sdk_installed
from .learning import LEARN_DIR, Learning, decisions
from .store import Workspace, atomic_write_json, check_id, read_json, now_iso as _now
from .i18n import AI_NAME_RULE, in_reply_language, tr

LESSONS_DIR = "lessons"
MAX_TURNS = 300           # most recent chat turns shown to the summariser
MAX_DECISIONS = 250       # review decisions shown to the summariser
MAX_RULES = 120           # existing rules shown for new / reinforce / conflict
MAX_LESSONS = 10
RELATIONS = ("new", "reinforce", "conflict")
VERDICTS = ("kept", "restored", "accepted", "declined", "added")

_STR = {"type": "string"}
REWRITE_TOOL = {
    "name": "submit_rule",
    "description": "Submit the standing editing rule as you understood it.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["title", "understood", "instruction", "same_as"],
        "properties": {"title": _STR, "understood": _STR, "instruction": _STR, "same_as": _STR},
    },
}
LESSONS_TOOL = {
    "name": "submit_lessons",
    "description": "Submit the editing habits this episode teaches (may be empty).",
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["lessons"],
        "properties": {"lessons": {"type": "array", "items": {
            "type": "object",
            "additionalProperties": False,
            "required": ["title", "instruction", "why", "relation", "related", "turns", "edits"],
            "properties": {
                "title": _STR, "instruction": _STR, "why": _STR,
                "relation": {"type": "string", "enum": list(RELATIONS)},
                "related": _STR,
                "turns": {"type": "array", "items": {"type": "integer"}},
                "edits": {"type": "array", "items": {"type": "string"}},
            }}}},
    },
}

SHOW = "Leon hosts 《洛城二三事》, a casual two-host Chinese film podcast with Pei; LACUNA is the AI producer that edits it with him."  # i18n-ignore

REWRITE_SYSTEM = SHOW + """ \
Leon asked LACUNA to remember something as a STANDING editing rule, one that applies to every future \
episode. Never store his words as they are: rewrite them into one clear rule and tell him how you read it, \
so he can confirm or correct it.

Return:
- title: the rule, one short line in Simplified Chinese, written as an editing instruction (who / what / how \
much), e.g. "Pei 的语气词「嗯」保留，不要删". No "记住", no quote marks around his words, no filler.
- understood: one or two sentences in Simplified Chinese, speaking to Leon ("我理解的是……"), saying what the \
rule covers, what it does not, and any assumption you made where he was vague.
- instruction: one English sentence telling an AI first-cut editor what to do differently.
- same_as: the id of an EXISTING rule (listed in the input) that already says the same thing, else "".

If the input has "current" and "feedback", Leon is correcting your previous version: apply his feedback to \
it (it may be a new wording he wants verbatim, or a change like "只针对 Pei"), and say in "understood" what \
changed. Use recent_chat only to resolve what "这个" or "这种" refers to.""" + AI_NAME_RULE  # i18n-ignore

LESSONS_SYSTEM = SHOW + """ \
Leon just finished editing one episode. From the chat log (what he asked LACUNA, its reply, whether he \
approved the change) and his review decisions (AI cuts he kept or restored, suggestions he accepted or \
declined, edits he asked for), work out the editing HABITS this episode teaches: things to do the same way \
in every future episode. A one-off fix of a single spot is not a habit unless it shows a general preference \
(for example the same kind of correction several times). Prefer a few solid lessons over many weak ones; \
none is a fine answer.

For each lesson return:
- title: the rule, one short line in Simplified Chinese, written as an editing instruction.
- instruction: one English sentence telling an AI first-cut editor what to do differently.
- why: one or two sentences in Simplified Chinese, speaking to Leon, with the evidence in words \
(e.g. "这一集 Pei 的 4 处「嗯」你都恢复了，第 12 句你也说过别删").
- relation: "new"; "reinforce" if an EXISTING rule (listed with its state) already says this; "conflict" if \
it contradicts an existing rule.
- related: the id of that existing rule for reinforce / conflict, else "".
- turns: the chat turn numbers it comes from; edits: the review edit ids it comes from. At least one of them.
Do not repeat anything in already_reviewed.""" + AI_NAME_RULE  # i18n-ignore


class NoAnswer(RuntimeError):
    """The model answered without calling the tool (or refused / ran out of room)."""


def ai_failure(e: Exception) -> str:
    """What went wrong, for Leon, in the interface language (never the raw API error)."""
    if isinstance(e, NoAnswer):
        return tr("LACUNA 这次没有给出结果")
    if type(e).__module__.startswith("anthropic"):
        return error_message(e, tail="")
    return tr("AI 服务出了点问题")


def _hid(*parts: str) -> str:
    return hashlib.sha1("\x1f".join(parts).encode()).hexdigest()[:10]


def _clean(s: Any, n: int = MAX_ASK) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()[:n]


# ============================================================================ the writer (AI)

class ClaudeRuleWriter:
    """Rewrites asks into rules and summarises an episode's lessons; `client` can be injected (tests)."""

    model = "claude-sonnet-5-5"

    def __init__(self, api_key: str | None = None, client: Any = None):
        self.api_key = api_key
        self._client = client

    def _key(self) -> str | None:
        return self.api_key or find_api_key()[0]      # a key saved in 设置 later counts without a restart

    @property
    def available(self) -> bool:
        return self._client is not None or (bool(self._key()) and sdk_installed())

    @property
    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self._key(), timeout=120.0, max_retries=1)
        return self._client

    def _call(self, system: str, tool: dict, payload: dict, max_tokens: int) -> tuple[dict, dict]:
        out, resp, seconds = call_tool(self.client.messages.create, dict(
            model=self.model, max_tokens=max_tokens, system=in_reply_language(system),
            tools=[in_reply_language(tool)],
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]), tool["name"])
        usage = ClaudeEditorAdapter._usage(resp, seconds)
        if out is None:
            raise NoAnswer(getattr(resp, "stop_reason", ""))
        return out, usage

    def rewrite(self, payload: dict) -> tuple[dict, dict]:
        return self._call(REWRITE_SYSTEM, REWRITE_TOOL, payload, 1000)

    def summarize(self, payload: dict) -> tuple[list[dict], dict]:
        out, usage = self._call(LESSONS_SYSTEM, LESSONS_TOOL, payload, 6000)
        return list(out.get("lessons") or []), usage


# ============================================================================ the service

class Lessons:
    def __init__(self, ws: Workspace, learning: Learning, asks: ChatAsks, writer: Any,
                 log_usage: Callable[[str, dict], None] = lambda e, u: None):
        self.ws, self.learning, self.asks, self.writer, self.log_usage = ws, learning, asks, writer, log_usage
        self.dir = ws.root / LEARN_DIR / LESSONS_DIR
        self.lock = threading.RLock()
        self.running: set[str] = set()

    # ---- storage
    def _path(self, episode_id: str):
        return self.dir / f"{check_id(episode_id)}.json"

    def load(self, episode_id: str) -> dict:
        p = self._path(episode_id)
        if not p.exists() and not p.with_name(p.name + ".bak").exists():
            return {"schema": 1, "episode": episode_id, "drafts": [], "summary": {"state": "none"}, "lessons": []}
        return read_json(p)

    def _save(self, episode_id: str, doc: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self._path(episode_id), doc)

    def _rules(self) -> list[dict]:
        """Existing rules (not deleted) as the AI sees them."""
        return [{"id": r["id"], "title": r["title"], "state": r["state"]}
                for r in self.learning.overview()["rules"]][:MAX_RULES]

    def _ask_rules(self) -> list[dict]:
        return [r for r in self._rules() if r["id"].startswith("ask:")]

    def _usage(self, episode_id: str, usage: dict | None, purpose: str) -> None:
        if usage:
            self.log_usage(episode_id, usage | {"purpose": purpose})

    def _adopt(self, episode_id: str, aid: str, title: str, instruction: str, source: str,
               quotes: list[dict]) -> str:
        """Store an ask under `aid` and put it in force (Leon has just confirmed it)."""
        self.asks.put(episode_id, {"id": aid, "title": title, "instruction": instruction, "source": source,
                                   "quotes": quotes[:6]})
        rid = f"ask:{aid}"
        self.learning.undelete(rid)
        self.learning.decide(rid, "approve")
        return rid

    # ================================================================ 「记住」 drafts (#9)
    def _rewrite(self, episode_id: str, payload: dict, fallback: str) -> dict:
        """The writer's rule, or (no key / it failed) his words for him to confirm or change."""
        if getattr(self.writer, "available", True):
            try:
                out, usage = self.writer.rewrite(payload)
                self._usage(episode_id, usage, "remember")
                title = _clean(out.get("title"))
                if title:
                    known = {r["id"].removeprefix("ask:") for r in payload["existing_rules"]}
                    same = str(out.get("same_as") or "").removeprefix("ask:")
                    return {"title": title, "understood": _clean(out.get("understood"), 600),
                            "instruction": _clean(out.get("instruction"), 600) or self._verbatim(title),
                            "same_as": same if same in known else "", "fallback": False, "error": ""}
            except Exception as e:         # noqa: BLE001 - he can still confirm his own words
                traceback.print_exc()
                return self._fallback(fallback, ai_failure(e))
        return self._fallback(fallback, "")

    def _fallback(self, words: str, error: str) -> dict:
        """His own words; `error` says why the AI didn't rewrite them ("" = no AI key)."""
        return {"title": words, "understood": "", "instruction": self._verbatim(words), "same_as": "",
                "fallback": True, "error": error}

    @staticmethod
    def _verbatim(title: str) -> str:
        return f'Leon\'s standing rule, in his words (Chinese): "{title}"'

    def _draft_view(self, d: dict) -> dict:
        titles = {r["id"].removeprefix("ask:"): r["title"] for r in self._ask_rules()}
        return d | {"same_as_title": titles.get(d.get("same_as") or "", "")}

    def remember(self, ep, said: str, at: float) -> dict:
        """A draft rule from what he asked to remember; nothing is stored as a rule yet."""
        said = _clean(said)
        recent = [{"leon_said": t["said"], "producer_replied": t.get("reply", "")[:200]}
                  for t in ep.chat_log()[-6:]]
        rule = self._rewrite(ep.id, {"said": said, "recent_chat": recent,
                                     "existing_rules": self._ask_rules()}, said)
        draft = {"id": _hid(ep.id, said, _now(), str(time.monotonic())), "said": said, "at": round(at, 2),
                 **rule, "state": "pending", "created": _now(), "history": []}
        with self.lock:
            doc = self.load(ep.id)
            doc["drafts"].append(draft)
            self._save(ep.id, doc)
        ep.log_turn(f"记住：{said}", at, rule["understood"] or rule["title"], remember=True)  # i18n-ignore
        return self._draft_view(draft)

    def _get(self, doc: dict, key: str, xid: str) -> dict:
        for x in doc[key]:
            if x["id"] == xid:
                return x
        raise KeyError(xid)

    def revise_draft(self, ep, did: str, feedback: str) -> dict:
        with self.lock:
            d = self._get(self.load(ep.id), "drafts", did)
        if d["state"] != "pending":
            raise ValueError("decided")
        feedback = _clean(feedback)
        current = {k: d[k] for k in ("title", "understood", "instruction")}
        rule = self._rewrite(ep.id, {"said": d["said"], "current": current, "feedback": feedback,
                                     "existing_rules": self._ask_rules()}, feedback)
        with self.lock:
            doc = self.load(ep.id)
            d = self._get(doc, "drafts", did)
            d["history"].append(current | {"feedback": feedback, "at": _now()})
            d.update(rule)
            self._save(ep.id, doc)
        return self._draft_view(d)

    def decide_draft(self, ep, did: str, action: str) -> dict:
        if action not in ("confirm", "drop"):
            raise ValueError(action)
        with self.lock:
            doc = self.load(ep.id)
            d = self._get(doc, "drafts", did)
            if d["state"] != "pending":
                return self._draft_view(d)
            if action == "confirm":
                aid = d.get("same_as") or ask_id(d["title"])
                d["rule"] = self._adopt(ep.id, aid, d["title"], d["instruction"], "remember",
                                        [{"said": f"记住：{d['said']}", "at": d["at"]}])  # i18n-ignore
            d["state"] = "confirmed" if action == "confirm" else "dropped"
            d["decided"] = _now()
            self._save(ep.id, doc)
        return self._draft_view(d)

    # ================================================================ 本集学到的规则 (#12)
    def _evidence(self, ep) -> tuple[list[dict], list]:
        log = ep.chat_log()
        ds = [d for d in decisions(ep) if d.verdict in VERDICTS]
        return log, ds

    @staticmethod
    def _sig(log: list[dict], ds: list) -> dict:
        return {"chat_turns": len(log), "decisions": hashlib.sha1(
            json.dumps(sorted((d.edit_id, d.verdict) for d in ds)).encode()).hexdigest()[:10]}

    def view(self, ep) -> dict:
        with self.lock:
            doc = self.load(ep.id)
        s = dict(doc.get("summary") or {"state": "none"})
        if ep.id in self.running:
            s["state"] = "running"
        if ep.meta.get("demo"):
            s["state"] = "demo"
        stale = False
        if s.get("state") == "done":
            log, ds = self._evidence(ep)
            stale = self._sig(log, ds) != s.get("sig")
        ids = {r["id"]: r for r in self.learning.overview()["rules"]}
        lessons = [x | {"rule_state": ids[x["rule"]]["state"] if x.get("rule") in ids else None}
                   for x in doc["lessons"]]
        error = s.get("error")
        if error and not s.get("friendly"):    # stored before errors were explained: never show the raw one
            error = tr("AI 服务出了点问题")
        return {"state": s["state"], "at": s.get("at"), "error": error, "stale": stale,
                "lessons": lessons, "pending": sum(x["state"] == "draft" for x in doc["lessons"])}

    def start(self, ep) -> dict:
        with self.lock:
            if ep.id not in self.running and not ep.meta.get("demo"):
                self.running.add(ep.id)
                threading.Thread(target=self._run, args=(ep,), name=f"lessons-{ep.id}", daemon=True).start()
        return self.view(ep)

    def _run(self, ep) -> None:
        try:
            self.summarize(ep)
        finally:
            with self.lock:
                self.running.discard(ep.id)

    def _set_summary(self, episode_id: str, **s) -> None:
        with self.lock:
            doc = self.load(episode_id)
            doc["summary"] = s | {"at": _now()}
            self._save(episode_id, doc)

    def summarize(self, ep) -> list[dict]:
        """One AI call over the whole episode; replaces earlier undecided lessons, keeps decided ones."""
        if not getattr(self.writer, "available", True):
            self._set_summary(ep.id, state="no_key")
            return []
        log, ds = self._evidence(ep)
        sig = self._sig(log, ds)
        shown, first = log[-MAX_TURNS:], max(len(log) - MAX_TURNS, 0)
        ds_shown = sorted(ds, key=lambda d: (d.how != "single", -d.length_s))[:MAX_DECISIONS]
        rules = self._rules()
        with self.lock:
            done = [x for x in self.load(ep.id)["lessons"] if x["state"] != "draft"]
        payload = {
            "episode": ep.meta.get("title") or ep.id,
            "chat": [{"turn": i + 1, "leon_said": t["said"], "producer_replied": t.get("reply", "")[:300],
                      "outcome": {"approved": "change approved", "discarded": "change rejected"}.get(
                          t.get("state", ""), "proposed, not decided" if t.get("proposal") else "no change")}
                     for i, t in enumerate(shown)],
            "review": [{"edit": d.edit_id, "kind": d.kind, "host": d.host, "verdict": d.verdict,
                        "how": d.how, "seconds": round(d.length_s, 1), "words": d.text, "ai_reason": d.reason}
                       for d in ds_shown],
            "existing_rules": rules,
            "already_reviewed": [{"title": x["title"], "decision": x["state"]} for x in done],
        }
        try:
            found, usage = self.writer.summarize(payload)
        except Exception as e:             # noqa: BLE001 - the step must never break the episode
            traceback.print_exc()
            self._set_summary(ep.id, state="error", error=ai_failure(e), friendly=True)
            return []
        self._usage(ep.id, usage, "lessons")
        by_rule = {r["id"]: r for r in rules}
        by_edit = {d.edit_id: d for d in ds}
        seen = {x["title"] for x in done}
        new = []
        for f in found[:MAX_LESSONS]:
            title, instr = _clean(f.get("title")), _clean(f.get("instruction"), 600)
            if not title or title in seen:
                continue                   # already decided in an earlier run (or said twice)
            seen.add(title)
            turns = []
            for n in f.get("turns") or []:
                i = first + int(n) - 1
                if first <= i < len(log):
                    turns.append({"turn": i + 1, "said": log[i]["said"][:MAX_ASK], "at": log[i].get("at", 0.0),
                                  "reply": (log[i].get("reply") or "")[:200]})
            edits = [{"edit": d.edit_id, "verdict": d.verdict, "kind": d.kind, "host": d.host, "text": d.text,
                      "seconds": round(d.length_s, 1), "raw": d.raw}
                     for e in dict.fromkeys(f.get("edits") or []) if (d := by_edit.get(str(e)))]
            if not turns and not edits:
                continue                   # every lesson must point at what actually happened
            rel = f.get("relation") if f.get("relation") in RELATIONS else "new"
            related = str(f.get("related") or "")
            if rel != "new" and related not in by_rule:
                rel, related = "new", ""
            new.append({"id": _hid(ep.id, title, _now(), str(len(new))), "title": title,
                        "instruction": instr or self._verbatim(title), "why": _clean(f.get("why"), 600),
                        "relation": rel, "related": related if rel != "new" else "",
                        "related_title": by_rule[related]["title"] if rel != "new" else "",
                        "turns": turns[:8], "edits": edits[:8], "state": "draft", "edited": False,
                        "reply": "", "history": []})
        with self.lock:
            doc = self.load(ep.id)
            doc["lessons"] = [x for x in doc["lessons"] if x["state"] != "draft"] + new
            doc["summary"] = {"state": "done", "at": _now(), "sig": sig, "found": len(new)}
            self._save(ep.id, doc)
        return new

    def edit_lesson(self, ep, lid: str, title: str) -> dict:
        title = _clean(title)
        if not title:
            raise ValueError("empty")
        with self.lock:
            doc = self.load(ep.id)
            x = self._get(doc, "lessons", lid)
            if x["state"] == "adopted":
                raise ValueError("decided")
            if title != x["title"]:
                x["history"].append({"title": x["title"], "instruction": x["instruction"], "by": "hand", "at": _now()})
                x["title"], x["instruction"], x["edited"], x["reply"] = title, self._verbatim(title), True, ""
                self._save(ep.id, doc)
        return x

    def revise_lesson(self, ep, lid: str, feedback: str) -> dict:
        with self.lock:
            x = self._get(self.load(ep.id), "lessons", lid)
        if x["state"] == "adopted":
            raise ValueError("decided")
        feedback = _clean(feedback)
        current = {"title": x["title"], "understood": x.get("why", ""), "instruction": x["instruction"]}
        rule = self._rewrite(ep.id, {"said": x["title"], "current": current, "feedback": feedback,
                                     "existing_rules": self._ask_rules()}, feedback)
        with self.lock:
            doc = self.load(ep.id)
            x = self._get(doc, "lessons", lid)
            x["history"].append(current | {"feedback": feedback, "by": "chat", "at": _now()})
            x.update(title=rule["title"], instruction=rule["instruction"], reply=rule["understood"],
                     edited=True, fallback=rule["fallback"], error=rule["error"])
            self._save(ep.id, doc)
        return x

    def decide_lesson(self, ep, lid: str, action: str) -> dict:
        if action not in ("adopt", "skip", "reopen"):
            raise ValueError(action)
        with self.lock:
            doc = self.load(ep.id)
            x = self._get(doc, "lessons", lid)
            if x["state"] == "adopted":
                return x                  # withdrawing happens on 学到的规则 only
            if action == "adopt":
                x["rule"] = self._adopt_lesson(ep.id, x)
                x["state"] = "adopted"
            else:
                x["state"] = "skipped" if action == "skip" else "draft"
            x["decided"] = _now()
            self._save(ep.id, doc)
        return x

    def _adopt_lesson(self, episode_id: str, x: dict) -> str:
        quotes = [{"said": t["said"], "at": t["at"]} for t in x["turns"]] or \
                 [{"said": e["text"] or e["kind"], "at": (e["raw"] or [0.0])[0]} for e in x["edits"]]
        rel, related = x["relation"], x.get("related") or ""
        rules = {r["id"]: r for r in self.learning.overview()["rules"]}
        keep_wording = rel == "reinforce" and not x.get("edited")
        if rel != "new" and related.startswith("ask:") and related in rules:
            aid = related.removeprefix("ask:")
            old = next((a for a in self.asks.all() if a["id"] == aid), None)
            if keep_wording and old:      # same wording, more evidence: the approval stays as it was
                return self._adopt(episode_id, aid, old["title"], old["instruction"], "lesson", quotes)
            # a new wording of the same ask replaces it (habits iterate; the old wording stays on file)
            return self._adopt(episode_id, aid, x["title"], x["instruction"], "lesson", quotes)
        if keep_wording and related in rules:      # a learned (non-chat) rule: adopting it is approving it
            if rules[related]["state"] != "approved":
                self.learning.decide(related, "approve")
            return related
        instr = x["instruction"]
        if rel == "conflict" and related in rules:
            instr = f'{instr} (This is newer than, and overrides, the rule "{rules[related]["title"]}".)'
        return self._adopt(episode_id, ask_id(x["title"]), x["title"], instr, "lesson", quotes)


__all__ = ["ClaudeRuleWriter", "Lessons", "REWRITE_TOOL", "LESSONS_TOOL"]
