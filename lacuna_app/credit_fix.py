"""一键修复曲名和作者 (decision 2026-10-30-credit-fix): LACUNA looks up the credits of an episode's own
music (on its music page) or of the shared music (on the library page) in one go, from the editor's one-line
description of where the music comes from, the file names, the embedded tags and the durations. The answers
wait as a list the editor ticks; only the ticked ones are written, as confirmed.

Only text goes to the API, never audio (same rule as `library.lookup_credit`). The lookup runs in the
background (web search can take a few minutes, longer than a request may stay open) and its result is kept
in ``library/.credit_fix/<key>.json``, so leaving the page or reloading does not lose it.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable

from . import show
from .i18n import AI_NAME_RULE, lang, speaking, tr
from .library import CONFIRMED, CREDIT_FIELDS, KINDS, LOOKUP_MODEL, Library, credit_line
from .store import atomic_write_json, now_iso, read_json

CHUNK = 12          # files per request: one soundtrack's track list usually answers all of them
MAX_FILES = 36      # per click; more than that is a library clean-up, not one episode
PICK_FROM = 0.7     # confidence at which a result starts ticked
STALE_S = 30 * 60   # a "running" file older than this (server restarted mid-run) counts as failed

SYSTEM = """\
You identify the music Leon uses in 《洛城二三事》, a Chinese film podcast, so the show notes can credit \
it correctly. You get Leon's one-line description of where this music comes from (may be empty) and a \
list of audio files: id, file name, the tags embedded in the file, duration, Leon's note on that file (often \
empty) and what it is used as. You cannot hear the audio. File names may be made up or wrong: Leon's \
description outranks them; embedded tags are usually right when present.

For each file find the official track: the exact title as released (original language), the composer (or \
performing artist for a song), the album, the film or series it belongs to (the title most commonly used \
in mainland China, in Simplified Chinese) and the release year. Use web search. When the description or \
the tags point to a soundtrack album, look up its official track list WITH durations (Apple Music, Spotify, \
Discogs, VGMdb, Wikipedia or the label) and match each file by duration, within about 3 seconds; a file \
Leon trimmed is shorter and will not match. One track list often answers several files, so search \
efficiently.

Never invent a title. When you cannot identify a file with reasonable confidence, return null title and \
film and say why in note. When two tracks fit about equally, put the more likely one in the fields, give \
a lower confidence and list the other(s) in alternatives as "title — composer". Then call submit_credits \
once, with exactly one item per file id.""" + AI_NAME_RULE  # i18n-ignore

NOTE_FOR = "one short sentence in Simplified Chinese for Leon: how you matched it, or why not"
TOOL = {
    "name": "submit_credits",
    "description": "Submit the identified tracks, one item per file id (null for anything not known).",
    "strict": True,
    "input_schema": {
        "type": "object", "additionalProperties": False, "required": ["items"],
        "properties": {"items": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["id", "title", "artist", "composer", "album", "film", "year", "confidence", "note",
                         "alternatives"],
            "properties": {
                "id": {"type": "string", "description": "the file id as given"},
                "title": {"type": ["string", "null"], "description": "official track title, original language"},
                "artist": {"type": ["string", "null"], "description": "performer, if a song"},
                "composer": {"type": ["string", "null"]},
                "album": {"type": ["string", "null"], "description": "soundtrack album title"},
                "film": {"type": ["string", "null"], "description": "film / series title in Simplified Chinese"},
                "year": {"type": ["integer", "null"]},
                "confidence": {"type": "number", "description": "0..1"},
                "note": {"type": "string", "description": NOTE_FOR},
                "alternatives": {"type": "array", "items": {"type": "string"}},
            },
        }}},
    },
}


def system_prompt(profile: dict | None) -> str:
    return show.neutral(SYSTEM, profile, [] if show.is_legacy(profile) else [
        ("the music Leon uses in 《洛城二三事》, a Chinese film podcast,",  # i18n-ignore
         f"the music used in 《{profile['show_name']}》, a podcast,"),
        ("Leon's", "the editor's"), ("Leon trimmed", "the editor trimmed"),
    ])


def tool(profile: dict | None) -> dict:
    """The note is for the editor, in the interface language; the credit itself stays as released."""
    out = json.dumps(TOOL)
    if lang() == "en":
        out = out.replace(NOTE_FOR, "one short sentence in English for Leon: how you matched it, or why not")
    if not show.is_legacy(profile):
        out = out.replace("for Leon", "for the editor")
    return json.loads(out)


def request(files: list[dict], prompt: str, profile: dict | None) -> dict:
    """One API request for up to CHUNK files."""
    legacy = show.is_legacy(profile)
    info = {("leons_description" if legacy else "editors_description"): prompt, "files": [{
        "id": a["id"], "file_name": a.get("name"), "embedded_tags": a.get("tags") or {},
        "duration_s": a.get("duration_s"), ("leons_note" if legacy else "editors_note"): a.get("note") or "",
        "used_as": KINDS.get(a.get("kind"), ""),
    } for a in files]}
    # Opus, like the single lookup: a wrong composer ends up in published show notes (quality first)
    return dict(model=LOOKUP_MODEL, max_tokens=32000, system=system_prompt(profile),
                output_config={"effort": "medium"},
                tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": min(15, 4 + 2 * len(files))},
                       tool(profile)],
                tool_choice={"type": "auto"},
                messages=[{"role": "user", "content": json.dumps(info, ensure_ascii=False)}])


def own_assets(lib: Library, episode: str | None) -> list[dict]:
    """What one click covers: with `episode`, the music only that episode has (uploaded on its music page);
    without, the library's shared music (whole show or an album). Oldest first, like the upload order."""
    out = []
    for a in lib.assets():
        if episode:
            if not a.get("shared") and episode in (a.get("episodes") or []):
                out.append(a)
        elif a.get("shared") or a.get("albums"):
            out.append(a)
    return sorted(out, key=lambda a: a.get("added_at") or "")


class CreditFixBusy(RuntimeError):
    pass


class CreditFixer:
    """One job per key ("ep_<episode id>" or "library"); the result waits on disk until applied or dropped."""

    def __init__(self, lib: Library, client: Any = None, on_usage: Callable[[str, dict], None] | None = None):
        self.lib, self.client, self.on_usage = lib, client, on_usage
        self.lock = threading.Lock()
        self.running: set[str] = set()

    @staticmethod
    def key(episode: str | None) -> str:
        return f"ep_{episode}" if episode else "library"

    def path(self, key: str):
        return self.lib.dir / ".credit_fix" / f"{key}.json"

    def available(self) -> bool:
        if self.client is not None:
            return True
        from .editor import find_api_key, sdk_installed
        return bool(find_api_key()[0]) and sdk_installed()

    # ------------------------------------------------------------------ what the page shows
    def targets(self, episode: str | None, redo: bool = False) -> list[dict]:
        return [a for a in own_assets(self.lib, episode) if redo or (a.get("credit") or {}).get("status") != CONFIRMED]

    def view(self, episode: str | None) -> dict:
        key = self.key(episode)
        mine = own_assets(self.lib, episode)
        todo = [a for a in mine if (a.get("credit") or {}).get("status") != CONFIRMED]
        out = {"available": self.available(), "own": len(mine), "unknown": len(todo),
               "files": [self._file(a) for a in mine], "job": None}
        job = self._load(key)
        if job is not None:
            if job.get("state") == "running" and key not in self.running:
                job = job | {"state": "failed", "message": tr("查到一半被打断了（服务器重启过），再点一次就好。")}
            out["job"] = job
        return out

    @staticmethod
    def _file(a: dict) -> dict:
        c = a.get("credit") or {}
        return {"id": a["id"], "name": a.get("name"), "duration_s": a.get("duration_s"),
                "kind_label": tr(KINDS.get(a.get("kind"), "")), "credit_line": credit_line(a),
                "status": c.get("status") or "unknown"}

    def _load(self, key: str) -> dict | None:
        p = self.path(key)
        if not p.is_file():
            return None
        try:
            job = read_json(p)
        except (OSError, ValueError):
            return None
        if job.get("state") == "running" and time.time() - float(job.get("t0") or 0) > STALE_S:
            job["state"] = "failed"
        return job

    def _save(self, key: str, job: dict) -> None:
        p = self.path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(p, job)

    # ------------------------------------------------------------------ run
    def start(self, episode: str | None, prompt: str, redo: bool = False) -> dict:
        key = self.key(episode)
        files = self.targets(episode, redo)[:MAX_FILES]
        if not files:
            raise ValueError(tr("没有要修的曲名：这里的歌都已经确认过了。"))
        if not self.available():
            raise ValueError(tr("还没接上 AI（没有 AI 密钥），没法查曲名。"))
        with self.lock:
            if key in self.running:
                raise CreditFixBusy(tr("LACUNA 正在查这一批，查完再点。"))
            self.running.add(key)
        prompt = prompt.strip()
        job = {"state": "running", "prompt": prompt, "redo": redo, "started_at": now_iso(), "t0": time.time(),
               "files": [self._file(a) for a in files], "results": [], "sources": [], "message": ""}
        self._save(key, job)
        profile = show.load(self.lib.ws.root)
        reqs = [request(files[i:i + CHUNK], prompt, profile) for i in range(0, len(files), CHUNK)]  # in this language
        speak = lang()

        def run():
            try:
                with speaking(speak):
                    self._run(key, job, files, reqs)
            finally:
                with self.lock:
                    self.running.discard(key)

        threading.Thread(target=run, name=f"credit-fix-{key}", daemon=True).start()
        return self.view(episode)

    def _client(self):
        if self.client is not None:
            return self.client
        import anthropic
        from .editor import find_api_key
        return anthropic.Anthropic(api_key=find_api_key()[0], timeout=300.0, max_retries=1)

    def _run(self, key: str, job: dict, files: list[dict], reqs: list[dict]) -> None:
        from .editor import ClaudeEditorAdapter, error_message
        by_id = {a["id"]: a for a in files}
        found: dict[str, dict] = {}
        sources: list[str] = []
        try:
            client = self._client()
            for req in reqs:
                t0 = time.monotonic()
                messages = list(req.pop("messages"))
                resp = None
                for _ in range(6):          # web search may pause a long turn; continue it
                    resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                                                       messages=messages, **req)
                    for block in resp.content:
                        if block.type == "web_search_tool_result" and isinstance(getattr(block, "content", None), list):
                            sources += [r.url for r in block.content if getattr(r, "url", None)]
                        if block.type == "tool_use" and block.name == "submit_credits":
                            for item in (block.input or {}).get("items") or []:
                                if isinstance(item, dict) and item.get("id") in by_id:
                                    found[item["id"]] = item
                    if resp.stop_reason != "pause_turn":
                        break
                    messages = messages + [{"role": "assistant", "content": resp.content}]
                if self.on_usage and resp is not None:
                    self.on_usage(key, ClaudeEditorAdapter._usage(resp, time.monotonic() - t0) | {"kind": "credit_fix"})
        except Exception as e:      # noqa: BLE001 - every failure becomes a message; nothing was changed
            job.update(state="failed", message=error_message(e, tail=tr("，曲名没有变。")), finished_at=now_iso())
            if found:               # what the finished requests found is still worth showing
                job.update(state="done", results=self._results(files, found))
            self._save(key, job)
            return
        results = self._results(files, found)
        hits = sum(1 for r in results if r["found"]["title"] or r["found"]["film"])
        job.update(state="done", results=results, sources=list(dict.fromkeys(sources))[:12], finished_at=now_iso(),
                   message=tr("查好了 {n} 首，{hits} 首有结果。", n=len(results), hits=hits) if results
                   else tr("LACUNA 没有给出曲名。"))
        self._save(key, job)

    @staticmethod
    def _results(files: list[dict], found: dict[str, dict]) -> list[dict]:
        out = []
        for a in files:
            f = found.get(a["id"]) or {}
            credit = {k: f.get(k) for k in CREDIT_FIELDS}
            y = credit["year"]
            credit["year"] = int(y) if isinstance(y, (int, float)) or str(y or "").isdigit() else None
            for k in CREDIT_FIELDS:
                if isinstance(credit[k], str):
                    credit[k] = credit[k].strip() or None
            known = bool(credit["title"] or credit["film"])
            conf = float(f.get("confidence") or 0) if known else 0.0
            out.append({
                "asset_id": a["id"], "name": a.get("name"), "duration_s": a.get("duration_s"),
                "old_line": credit_line(a), "old_status": (a.get("credit") or {}).get("status") or "unknown",
                "found": credit, "line": credit_line({"name": a.get("name"), "credit": credit}) if known else "",
                "confidence": round(conf, 2), "note": str(f.get("note") or ("" if f else tr("LACUNA 没有回答这一首。"))),
                "alternatives": [str(x) for x in (f.get("alternatives") or []) if str(x).strip()][:4],
                "pick": known and conf >= PICK_FROM,
            })
        return out

    # ------------------------------------------------------------------ apply / drop
    def apply(self, episode: str | None, picks: list[dict]) -> int:
        """Write the ticked credits (as the editor left them in the list) as confirmed; drops the result."""
        key = self.key(episode)
        if key in self.running:
            raise CreditFixBusy(tr("LACUNA 还在查，查完再采用。"))
        job = self._load(key) or {}
        sources = job.get("sources") or []
        n = 0
        for p in picks:
            credit = {k: p.get("credit", {}).get(k) for k in CREDIT_FIELDS}
            if not (credit["title"] or credit["film"]):
                continue
            try:
                self.lib.set_credit(str(p.get("asset_id")), credit, source="claude", sources=sources)
            except KeyError:
                continue                    # taken out of the library meanwhile
            n += 1
        self.discard(episode)
        return n

    def discard(self, episode: str | None) -> None:
        key = self.key(episode)
        if key in self.running:
            raise CreditFixBusy(tr("LACUNA 还在查，查完再采用。"))
        try:
            self.path(key).unlink()
        except FileNotFoundError:
            pass
