"""Proper-noun check of the transcript at import (Leon 2026-10-31): the show-notes 专有名词核对, moved to
the start, so 审阅 / 整集试听 and the AI first cut already read the right names and the show notes do not
have to ask again.

``transcript_fix.py`` proofreads the show's OWN names (hosts, show, 项目设置 terms). This pass looks for
every other proper noun the recogniser mis-heard (films, people, places, works...), with the model's
own knowledge, the way the show-notes writer flagged ``names_to_check``. Same safety rules
(decision `transcript-audio-first`): ``wrong`` must be whole words of that line and must SOUND like
``right`` (``transcript_fix.sounds_alike``); only word text changes, every start / end time stays, so
cuts, edits and the audio are untouched and no word is added.

The fixes are applied without asking (on by default, 项目设置 → 「导入时核对专有名词」 turns it off) and
listed on the episode (``<episode>/name_check.json``), where each can be put back as heard
(routes/name_check.py). Put back pairs are remembered in ``<workspace>/name_keep.json``: later imports
and the show notes leave them alone. Any failure, timeout or missing key leaves the text as heard: an
import never fails or waits because of this. Only text leaves the server.
"""
from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from . import show
from . import transcript_fix as tf
from .editor import ClaudeEditorAdapter, find_api_key, sdk_installed

MODEL = ClaudeEditorAdapter.model      # quality first (Leon): the same top model as the show notes
TIMEOUT_S = 180.0
CHUNK_CHARS = 9000
WORKERS = 4
MAX_RIGHT = 40
IMPORT_FILE = "name_fixes.json"        # <imports>/<episode>/: the model's checked answer (a resumed import asks once)
EPISODE_FILE = "name_check.json"       # <episode>/: what was changed, for the interface
KEEP_FILE = "name_keep.json"           # <workspace>/: pairs put back as heard

SYSTEM = (Path(__file__).resolve().parent / "prompts" / "name_check.txt").read_text(encoding="utf-8").strip()

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["fixes"],
    "properties": {"fixes": {"type": "array", "items": {
        "type": "object",
        "additionalProperties": False,
        "required": ["line", "wrong", "right", "why"],
        "properties": {"line": {"type": "string", "description": "line id, e.g. L0012"},
                       "wrong": {"type": "string", "description": "the mis-heard characters, copied from the line"},
                       "right": {"type": "string", "description": "the proper noun as it should be written"},
                       "why": {"type": "string", "description": "what it is, a few words of Simplified Chinese"}}}}},
}


def enabled(root: str | Path) -> bool:
    """On unless the project turned it off, or LACUNA_NAME_CHECK=off."""
    if os.environ.get("LACUNA_NAME_CHECK", "on").strip().lower() in ("0", "off", "false", "no"):
        return False
    return show.load(root).get("name_check", True) is not False


# ---------------------------------------------------------------------------- put back as heard

def kept(root: str | Path) -> list[dict]:
    """[{"wrong", "right"}]: fixes the editor put back (heard text kept)."""
    from .store import read_json
    p = Path(root) / KEEP_FILE
    try:
        return [{"wrong": str(k["wrong"]), "right": str(k["right"])} for k in read_json(p).get("keep", [])
                if k.get("wrong") and k.get("right")] if p.is_file() else []
    except (OSError, ValueError, AttributeError, TypeError, KeyError):
        return []


def keep(root: str | Path, wrong: str, right: str) -> None:
    from .store import atomic_write_json
    rows = kept(root)
    if not any(tf._key(k["wrong"]) == tf._key(wrong) and tf._key(k["right"]) == tf._key(right) for k in rows):
        rows.append({"wrong": wrong, "right": right})
    atomic_write_json(Path(root) / KEEP_FILE, {"keep": rows[-500:]})


def is_kept(rows: list[dict], wrong: str, right: str) -> bool:
    return any(tf._key(k["wrong"]) == tf._key(wrong) and tf._key(k["right"]) == tf._key(right) for k in rows)


# ---------------------------------------------------------------------------- checking answers

def check(fixes: list[dict], lines: list[tf.Line], keep_rows: list[dict] = ()) -> list[dict]:
    """Only answers that quote whole words of that line, sound like the name and were not put back before."""
    by_id = {ln.id: ln for ln in lines}
    out, seen = [], set()
    for f in fixes:
        try:
            line, wrong, right = str(f["line"]).strip(), str(f["wrong"]).strip(), str(f["right"]).strip()
            why = str(f.get("why") or "").strip()[:80]
        except (KeyError, TypeError):
            continue
        right = right.strip("《》「」“”\"'")
        ln = by_id.get(line)
        if ln is None or not wrong or not right or len(right) > MAX_RIGHT or tf._key(wrong) == tf._key(right):
            continue
        if len(tf._key(wrong)) > 3 * len(tf._key(right)) + 6:      # a whole clause is not a mis-heard name
            continue
        if not tf.find_spans(ln.words, wrong) or not tf.sounds_alike(wrong, right):
            continue
        if is_kept(list(keep_rows), wrong, right):
            continue
        k = (line, tf._key(wrong), right)
        if k not in seen:
            seen.add(k)
            out.append({"line": line, "wrong": wrong, "right": right, "why": why})
    return out


def usage_of(resp, seconds: float) -> dict:
    return {**tf.usage_of(resp, seconds), "kind": "name_check"}


class NameChecker:
    """`client` can be injected (tests use a fake with ``messages.create``)."""

    model = MODEL

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
            self._client = anthropic.Anthropic(api_key=self.api_key, timeout=TIMEOUT_S, max_retries=1)
        return self._client

    def request(self, part: list[tf.Line], context: dict) -> dict:
        doc = {**context, "lines": [f"{ln.id} {ln.speaker}：{ln.text}" for ln in part]}
        return dict(model=self.model, max_tokens=6000, system=SYSTEM,
                    output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
                    messages=[{"role": "user", "content": json.dumps(doc, ensure_ascii=False)}])

    def _ask(self, part: list[tf.Line], context: dict, on_usage: Callable[[dict], None]) -> list[dict] | None:
        t0 = time.monotonic()
        try:
            resp = self.client.messages.create(**self.request(part, context))
        except Exception:          # noqa: BLE001 - checking names must never break an import
            return None
        try:
            on_usage(usage_of(resp, time.monotonic() - t0))
        except Exception:          # noqa: BLE001
            pass
        if getattr(resp, "stop_reason", "") == "refusal":
            return []
        try:
            text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            return list(json.loads(text).get("fixes") or [])
        except (ValueError, AttributeError, TypeError):
            return None

    def propose(self, lines: list[tf.Line], root: str | Path, title: str = "",
                on_usage: Callable[[dict], None] = lambda u: None) -> list[dict]:
        """Checked fixes for `lines` ([] when the model is not reachable)."""
        if not self.available or not lines:
            return []
        profile = show.load(root)
        keep_rows = kept(root)
        g = tf.glossary_for(root, title)
        context = {"show": profile.get("show_name") or "", "about": profile.get("about") or "", "episode_title": title,
                   "known": {"spellings": g.terms[:120],
                             "leave_as_heard": [f"{k['wrong']} (not {k['right']})" for k in keep_rows][-100:]}}
        parts = tf.chunks(lines, CHUNK_CHARS)
        out: list[dict] = []
        with ThreadPoolExecutor(min(WORKERS, len(parts)), thread_name_prefix="name-check") as pool:
            for answer in pool.map(lambda p: self._ask(p, context, on_usage), parts):
                out += check(answer or [], lines, keep_rows)
        return out


def record(done: list[dict], fixes: list[dict], lines: list[tf.Line]) -> list[dict]:
    """What the interface lists: one row per (wrong, right) with its places, from tf.apply's `done`."""
    why = {(f["wrong"], f["right"]): f.get("why", "") for f in fixes}
    by_id = {ln.id: ln for ln in lines}
    rows: dict[tuple[str, str], dict] = {}
    for f in done:
        ln = by_id.get(f["line"])
        k = (f["wrong"], f["right"])
        r = rows.setdefault(k, {"wrong": f["wrong"], "right": f["right"], "why": why.get(k, ""), "count": 0,
                                "places": [], "state": "applied"})
        r["count"] += int(f.get("count", 1))
        if ln is not None and ln.words:
            r["places"].append({"speaker": ln.speaker, "start": round(float(ln.words[0]["start"]), 2),
                                "end": round(float(ln.words[-1]["end"]), 2)})
    return sorted(rows.values(), key=lambda r: r["places"][0]["start"] if r["places"] else 0.0)
