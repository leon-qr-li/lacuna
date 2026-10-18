"""Publish pack (phase 9, D40): title, blurb, show notes and chapters on the final-cut timeline.

Flow
----
* ``segments`` reads the episode's transcript *as it sounds on the current cut* (cuts, lifts and
  slips applied) and groups it into numbered segments. Every segment keeps an anchor in **base**
  time (the uncut recording), so its position on any later version of the cut is a local lookup.
* Claude gets only text (the segments with their final-cut times, names Leon corrected before,
  the approved EP001 example) and answers through a strict tool. Timeline entries cite segment ids;
  the times are computed here, never written by the model (same principle as D37).
* ``render_markdown`` lays the structured draft out in the approved format (D40, example in
  ``prompts/show_notes_example.md``). Leon may edit the Markdown in the app; a later re-timing
  (after more edits) only swaps the bold timestamps, so his wording stays.
* BGM credits and the shift from inserted music come from the media library (phase 6a,
  ``lacuna_app.music``) through ``music_info``; until it exists the BGM section shows a placeholder.

Persistence (D42): ``<episode>/publish.json`` through ``store``; every save also writes the
Markdown to ``<workspace>/exports/<episode>/publish/notes.md`` for copying into 喜马拉雅.
Corrected names go to ``<workspace>/names.json`` and are applied to the next episode's transcript.
"""
from __future__ import annotations

import os
import re
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .editor import ClaudeEditorAdapter, error_message, find_api_key, sdk_installed
from .episode import Episode, to_base, to_tl
from .store import PUBLISH_FILE, Workspace, atomic_write_json, inside, read_json, now_iso
from .i18n import AI_NAME_RULE, tr

PUBLISH_SCHEMA = 1
NAMES_SCHEMA = 1
NAMES_FILE = "names.json"
PROMPTS = Path(__file__).resolve().parent / "prompts"
SHOW = "洛城二三事"  # i18n-ignore
FOOTER = "*《洛城二三事》是 Leon 和 Pei 两个人的电影闲聊。觉得好听，就分享给一个也爱看电影的朋友吧。*"  # i18n-ignore
ROLE_LABELS = {"intro": "片头", "interlude": "间奏", "outro": "片尾", "bed": "铺底", "clip": "台词"}  # i18n-ignore
MERGE_GAP_S = 1.5          # same speaker, shorter gap -> same segment
MAX_SEGMENT_S = 45.0
MIN_CHARS = 3              # "嗯" / "对对" alone are not worth a line

_STR = {"type": "string"}
_STRS = {"type": "array", "items": _STR}
TOOL = {
    "name": "submit_publish_pack",
    "description": "Submit the episode title, blurb, show-notes intro, timeline and references.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["title", "alt_titles", "blurb", "intro", "sections", "films", "shows", "things",
                     "glossary", "names_to_check"],
        "properties": {
            "title": _STR,
            "alt_titles": _STRS,
            "blurb": _STR,
            "intro": {"type": "string", "description": "Markdown paragraphs (+ optional bullets), no headings"},
            "sections": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["heading", "entries"],
                "properties": {
                    "heading": _STR,
                    "entries": {"type": "array", "items": {
                        "type": "object", "additionalProperties": False, "required": ["segment", "text"],
                        "properties": {"segment": {"type": "string", "description": "segment id, e.g. s0042"},
                                       "text": _STR}}}}}},
            "films": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["name", "note"],
                "properties": {"name": _STR, "note": _STR}}},
            "shows": _STRS,
            "things": _STRS,
            "glossary": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["term", "meaning"],
                "properties": {"term": _STR, "meaning": _STR}}},
            "names_to_check": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["heard", "suggested", "segment", "why"],
                "properties": {"heard": _STR, "suggested": _STR, "segment": {"type": ["string", "null"]},
                               "why": _STR}}},
        },
    },
}


class PublishError(RuntimeError):
    pass


class PublishBusy(RuntimeError):
    pass


# ---------------------------------------------------------------------------- time helpers

def mmss(s: float) -> str:
    """0:41 -> "00:41"; past an hour "1:02:03" (both parsed as timestamps by 小宇宙)."""
    s = int(max(s, 0.0))
    h, m, sec = s // 3600, s % 3600 // 60, s % 60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def episode_label(episode_id: str) -> str:
    m = re.match(r"(EP\d+)", episode_id, re.I)
    return m.group(1).upper() if m else episode_id


# ---------------------------------------------------------------------------- music (phase 6a)

@dataclass
class Music:
    """Music placed in this episode, from the 6a media library (``lacuna_app.music``).

    credits: ``music.bgm_credits`` rows in final-cut order (role, role_label, start_s / end_s on the
    final mixed timeline, credit_line, credit_status ...), or None while there is no library.
    to_final: ``music.final_time`` - voice-cut seconds -> final seconds (inserted intro/interludes)."""
    credits: list[dict] | None = None
    to_final: Callable[[float], float] = lambda t: t
    inserts: list[list[float]] | None = None   # time music adds to the talk: [voice s, length s]

    @property
    def library(self) -> bool:
        return self.credits is not None


def music_info(ws: Workspace, ep: Episode) -> Music:
    """The episode's music layout, built once: ``music.credits`` (same rows as ``music.bgm_credits``)
    and its voice -> final mapping (same as ``music.final_time``) without re-reading per call."""
    try:
        from . import music  # type: ignore[attr-defined]
    except Exception:          # noqa: BLE001 - 6a not on this install
        return Music()
    try:
        with ep.lock:
            lay = music.EpisodeMusic(ws, ep).layout()
        credits = []
        for c in music.credits(lay) or []:
            credits.append({"role": str(c.get("role") or "clip"),
                            "role_label": str(c.get("role_label") or ROLE_LABELS.get(c.get("role"), "配乐")),  # i18n-ignore
                            "start_s": round(float(c.get("start_s") or 0.0), 3),
                            "end_s": round(float(c.get("end_s") or 0.0), 3),
                            "credit_line": str(c.get("credit_line") or c.get("title") or ""),
                            "credit_status": str(c.get("credit_status") or "unknown")})
    except Exception:          # noqa: BLE001 - a library problem must not break the show notes
        traceback.print_exc()
        return Music()
    sr = lay.sr
    inserts = [[round(T / sr, 3), round(n / sr, 3)] for T, _, n in lay.inserts if n > 0]
    return Music(credits, lambda t: lay.final(int(round(t * sr))) / sr, inserts)


# ---------------------------------------------------------------------------- names (词表)

def load_names(ws: Workspace) -> list[dict]:
    p = ws.root / NAMES_FILE
    if not p.is_file():
        return []
    try:
        d = read_json(p)
    except (OSError, ValueError):
        return []
    return [n for n in d.get("names", []) if n.get("wrong") and n.get("right")]


def add_name(ws: Workspace, wrong: str, right: str) -> None:
    names = [n for n in load_names(ws) if n["wrong"] != wrong]
    names.append({"wrong": wrong, "right": right, "at": now_iso()})
    atomic_write_json(ws.root / NAMES_FILE, {"schema": NAMES_SCHEMA, "names": names})


def apply_names(text: str, names: list[dict]) -> str:
    for n in sorted(names, key=lambda n: -len(n["wrong"])):
        text = text.replace(n["wrong"], n["right"])
    return text


# ---------------------------------------------------------------------------- segments

@dataclass
class Segment:
    id: str
    speaker: str
    start: float           # voice-cut seconds (version it was read from)
    end: float
    base_s: float          # anchor in the uncut recording
    text: str


def segments(ep: Episode) -> list[Segment]:
    """The current cut's transcript as numbered segments (one host, no long gap, ≤ 45 s)."""
    with ep.lock:
        enabled = ep.enabled
        cuts = ep.cuts_for(enabled)
        dur = ep.timeline_for(enabled).length / ep.sr
        utts = ep.utterances(0.0, dur, enabled, cuts)
    groups: list[list] = []
    for u in utts:                       # time order; a short interjection of the other host splits
        g = groups[-1] if groups else None
        if g and g[0].speaker == u.speaker and u.start - g[-1].end < MERGE_GAP_S and u.end - g[0].start < MAX_SEGMENT_S:
            g.append(u)
        else:
            groups.append([u])
    out = []
    for g in groups:
        text = "".join(u.text for u in g)
        if len(text) < MIN_CHARS:
            continue
        start = g[0].start
        out.append(Segment(f"s{len(out) + 1:04d}", g[0].speaker, round(start, 3), round(g[-1].end, 3),
                           round(to_base(int(start * ep.sr), cuts) / ep.sr, 3), text))
    return out


def transcript_doc(segs: list[Segment], music: Music, names: list[dict]) -> str:
    return "\n".join(f"{s.id} {mmss(music.to_final(s.start))} {s.speaker}：{apply_names(s.text, names)}"
                     for s in segs)


# ---------------------------------------------------------------------------- writers

@dataclass
class Draft:
    data: dict                                   # the tool answer, cleaned
    usage: dict = field(default_factory=dict)
    adapter: str = "claude"
    notes: list[str] = field(default_factory=list)


def user_message(ep: Episode, doc: str, duration: float, names: list[dict]) -> str:
    known = "\n".join(f"- {n['wrong']} → {n['right']}" for n in names) or "（还没有）"  # i18n-ignore
    return (f"节目：《{SHOW}》 {episode_label(ep.id)}，剪辑里的标题：{ep.meta.get('title', ep.id)}\n"  # i18n-ignore
            f"成品时长：{mmss(duration)}\n\nLeon 以前改过的名字（错 → 对）：\n{known}\n\n"  # i18n-ignore
            f"成品转写（每行：段落编号 成品时间 说话人：内容）：\n{doc}\n\n"  # i18n-ignore
            "请按说明写这一期的发布资料，调用 submit_publish_pack 一次。")  # i18n-ignore


class ClaudePublisher:
    """One streamed request; `client` can be injected (tests use a fake)."""

    name = "claude"
    model = ClaudeEditorAdapter.model

    def __init__(self, api_key: str | None = None, client: Any = None, effort: str | None = None):
        if api_key is None and client is None:
            api_key, _ = find_api_key()
        self.api_key = api_key
        self._client = client
        self.effort = effort or os.environ.get("LACUNA_PUBLISH_EFFORT", "medium")

    @property
    def available(self) -> bool:
        return self._client is not None or (bool(self.api_key) and sdk_installed())

    @property
    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key, timeout=600.0, max_retries=2)
        return self._client

    @staticmethod
    def system() -> str:
        return ((PROMPTS / "show_notes_brief.txt").read_text(encoding="utf-8")
                + "\n\nAPPROVED EXAMPLE (EP001, format and voice only):\n\n"
                + (PROMPTS / "show_notes_example.md").read_text(encoding="utf-8") + AI_NAME_RULE)

    def request(self, user: str) -> dict:
        return dict(model=self.model, max_tokens=32000, system=self.system(),
                    output_config={"effort": self.effort}, tools=[TOOL], tool_choice={"type": "auto"},
                    messages=[{"role": "user", "content": user}])

    def write(self, ep: Episode, segs: list[Segment], music: Music, names: list[dict],
              duration: float) -> Draft:
        user = user_message(ep, transcript_doc(segs, music, names), duration, names)
        t0 = time.monotonic()
        try:
            with self.client.beta.messages.stream(betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                                                  **self.request(user)) as s:
                resp = s.get_final_message()
        except Exception as e:      # noqa: BLE001
            raise PublishError(error_message(e, tail="")) from e
        usage = ClaudeEditorAdapter._usage(resp, time.monotonic() - t0)
        if resp.stop_reason == "refusal":
            raise PublishError(tr("LACUNA 没有处理这次请求"))
        for block in resp.content:
            if block.type == "tool_use" and block.name == "submit_publish_pack":
                return Draft(dict(block.input), usage, self.name)
        if resp.stop_reason == "max_tokens":
            raise PublishError(tr("回答太长被截断了"))
        raise PublishError(tr("LACUNA 没有交回发布资料"))


class RulePublisher:
    """Offline fallback (no key / no SDK): a skeleton cut by time, clearly labelled as such."""

    name = "rules"
    available = True

    def write(self, ep: Episode, segs: list[Segment], music: Music, names: list[dict],
              duration: float) -> Draft:
        sections: list[dict] = []
        last = -1e9
        for s in segs:
            part = int(s.start // 600)
            if not sections or sections[-1]["_part"] != part:
                sections.append({"_part": part, "heading": f"第 {part + 1} 部分", "entries": []})  # i18n-ignore
            if s.start - last >= 180:
                sections[-1]["entries"].append({"segment": s.id, "text": apply_names(s.text, names)[:24] + "…"})
                last = s.start
        for sec in sections:
            del sec["_part"]
        title = ep.meta.get("title", ep.id)
        data = {"title": title, "alt_titles": [], "blurb": "",
                "intro": "（AI 没接上：这是按时间切的草稿，开场白、片名表和小词典要接上 AI 才会写。）",  # i18n-ignore
                "sections": sections, "films": [], "shows": [], "things": [], "glossary": [], "names_to_check": []}
        return Draft(data, {}, self.name, [tr("还没接上 AI（没有 AI 密钥），只生成了按时间切的草稿。")])


def make_publisher(kind: str = "auto"):
    if kind == "rules":
        return RulePublisher()
    c = ClaudePublisher()
    if kind == "claude" or c.available:
        return c
    return RulePublisher()


# ---------------------------------------------------------------------------- draft -> pack

def _s(v: Any, limit: int = 2000) -> str:
    return str(v or "").strip()[:limit]


def clean(data: dict, segs: list[Segment]) -> tuple[dict, list[str]]:
    """Keep only well-formed fields; timeline entries must cite a segment that exists."""
    by_id = {s.id: s for s in segs}
    notes: list[str] = []
    dropped = 0
    sections = []
    for sec in data.get("sections") or []:
        entries = []
        for e in sec.get("entries") or []:
            s = by_id.get(_s(e.get("segment")))
            text = _s(e.get("text"), 200)
            if s is None or not text:
                dropped += 1
                continue
            entries.append({"text": text, "base_s": s.base_s, "segment": s.id})
        entries.sort(key=lambda e: e["base_s"])
        if entries:
            sections.append({"heading": _s(sec.get("heading"), 200) or "（未命名）", "entries": entries})  # i18n-ignore
    sections.sort(key=lambda sec: sec["entries"][0]["base_s"])
    if dropped:
        notes.append(tr("有 {dropped} 条时间轴引用了不存在的段落，已丢掉。", dropped=dropped))
    names = []
    for n in data.get("names_to_check") or []:
        heard, sug = _s(n.get("heard"), 100), _s(n.get("suggested"), 100)
        if heard and sug and heard != sug:
            seg = by_id.get(_s(n.get("segment")))
            names.append({"heard": heard, "suggested": sug, "why": _s(n.get("why"), 300),
                          "base_s": seg.base_s if seg else None, "state": "open"})
    out = {
        "title": _s(data.get("title"), 200),
        "alt_titles": [t for t in (_s(x, 200) for x in data.get("alt_titles") or []) if t][:6],
        "blurb": _s(data.get("blurb"), 300),
        "intro": _s(data.get("intro"), 6000),
        "sections": sections,
        "films": [{"name": _s(f.get("name"), 200), "note": _s(f.get("note"), 200)}
                  for f in data.get("films") or [] if _s(f.get("name"))],
        "shows": [t for t in (_s(x, 200) for x in data.get("shows") or []) if t],
        "things": [t for t in (_s(x, 200) for x in data.get("things") or []) if t],
        "glossary": [{"term": _s(g.get("term"), 100), "meaning": _s(g.get("meaning"), 300)}
                     for g in data.get("glossary") or [] if _s(g.get("term"))],
        "names": names,
    }
    return out, notes


def timed(ep: Episode, draft: dict, music: Music) -> dict:
    """Times of every timeline entry and music cue on the current cut (no API call)."""
    with ep.lock:
        cuts = ep.cuts_for(ep.enabled)
    sr = ep.sr
    rows = []            # {"key", "t", "text", "section", "gone"} in time order
    for si, sec in enumerate(draft["sections"]):
        for ei, e in enumerate(sec["entries"]):
            x = int(e["base_s"] * sr)
            gone = any(a <= x < b for a, b in cuts)
            rows.append({"key": f"{si}.{ei}", "t": music.to_final(to_tl(x, cuts) / sr), "text": e["text"],
                         "section": si, "gone": gone})
    speech = list(rows)
    for ci, c in enumerate(c for c in music.credits or () if c["role"] in ("intro", "interlude", "outro")):
        t = c["start_s"]
        # the music line goes to the part playing at that moment (intro: the first, outro: the last)
        sec = 0
        for r in speech:
            if r["t"] <= t + 1e-6:
                sec = max(sec, r["section"])
        if c["role"] == "outro" and speech:
            sec = max(r["section"] for r in speech)
        elif c["role"] == "intro":
            sec = 0
        label = {"intro": "片头", "interlude": "🎵 间奏", "outro": "片尾"}[c["role"]]  # i18n-ignore
        rows.append({"key": f"m{ci}", "t": t, "text": label, "section": sec, "gone": False, "music": True})
    rows.sort(key=lambda r: (r["section"], r["t"], 0 if r.get("music") else 1))
    return {"rows": rows}


# ---------------------------------------------------------------------------- markdown

def bgm_lines(credits: list[dict] | None) -> list[str]:
    if credits is None:
        return ["- （素材库还没接上：配乐放进这一集后，这里自动填曲名）"]  # i18n-ignore
    if not credits:
        return ["- BGM：未设置"]  # i18n-ignore
    out = []
    for c in credits:
        label = c["role_label"]
        if c["role"] not in ("intro", "outro"):
            label = f"{mmss(c['start_s'])} {label}"
        line = c["credit_line"] or "（曲名待补：在素材库里填上正式曲名）"  # i18n-ignore
        if c["credit_status"] == "suggested":
            line += "（曲名待确认）"  # i18n-ignore
        out.append(f"- **{label}**：{line}")
    return out


def render_markdown(episode_id: str, draft: dict, rows: list[dict], credits: list[dict] | None) -> str:
    L = [f"# {draft['title'] or episode_id}", "", f"> 《{SHOW}》{episode_label(episode_id)} · Leon & Pei", ""]
    if draft["intro"]:
        L += [draft["intro"], ""]
    L += ["---", "", "## ⏱ 时间轴", ""]  # i18n-ignore
    for si, sec in enumerate(draft["sections"]):
        L.append(f"### {sec['heading']}")
        L += [f"- **{mmss(r['t'])}** {r['text']}" for r in rows if r["section"] == si]
        L.append("")
    L += ["---", ""]
    if draft["films"]:
        L += ["## 🎬 本期提到的电影", ""]  # i18n-ignore
        L += [f"- {f['name']}：{f['note']}" if f["note"] else f"- {f['name']}" for f in draft["films"]]
        L.append("")
    if draft["shows"]:
        L += [f"**剧集 / 纪录片 / 游戏**：{' · '.join(draft['shows'])}", ""]  # i18n-ignore
    if draft["things"]:
        L += ["## 🎨 本期提到的人和东西", "", " · ".join(draft["things"]), ""]  # i18n-ignore
    if draft["glossary"]:
        L += ["## 😏 内部梗小词典", ""]  # i18n-ignore
        L += [f"- **{g['term']}**：{g['meaning']}" for g in draft["glossary"]]
        L.append("")
    L += ["## 🎵 本期 BGM", ""] + bgm_lines(credits) + ["", "---", "", FOOTER, ""]  # i18n-ignore
    return "\n".join(L)


_PIPE = re.compile(r"(?<!\\)\|")          # a cell border; "\|" is a pipe inside a cell
_TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def _row(line: str) -> list[str] | None:
    """The cells of a table row (outer pipes optional), or None if the line has no cell border."""
    if not _PIPE.search(line):
        return None
    s = line.strip()
    s = s[1:] if s.startswith("|") else s
    s = s[:-1] if s.endswith("|") and not s.endswith("\\|") else s
    return [c.strip().replace("\\|", "|") for c in _PIPE.split(s)]


def untable(md: str) -> str:
    """喜马拉雅 has no tables (item 26): every Markdown table becomes one list line per row,
    "- first：rest · rest"; the header row is only labels, so it goes."""
    lines = md.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        if (_row(lines[i]) and i + 1 < len(lines) and "|" in lines[i + 1]
                and _TABLE_RULE.match(lines[i + 1])):
            i += 2
            while i < len(lines) and (cells := _row(lines[i])) is not None:
                cells = [c for c in cells if c]
                if cells:
                    out.append(f"- {cells[0]}" + (f"：{' · '.join(cells[1:])}" if len(cells) > 1 else ""))
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def has_table(md: str) -> bool:
    return untable(md) != md


_BOLD_TIME = re.compile(r"\*\*(\d{1,2}:\d{2}(?::\d{2})?)\*\*")


def retime_markdown(md: str, old: list[str], new: list[str]) -> str:
    """Swap the bold timestamps of Leon's edited Markdown in order: the k-th bold time that still
    reads like the k-th old time becomes the k-th new one; anything he added himself stays."""
    pairs = list(zip(old, new))
    k = 0

    def sub(m: re.Match) -> str:
        nonlocal k
        for j in range(k, len(pairs)):
            if pairs[j][0] == m.group(1):
                k = j + 1
                return f"**{pairs[j][1]}**"
        return m.group(0)
    return _BOLD_TIME.sub(sub, md)


# ---------------------------------------------------------------------------- the pack on disk

class Publisher:
    """Publish packs of a workspace: background generation, local re-timing, Leon's edits."""

    def __init__(self, ws: Workspace, factory: Callable[[], Any] = make_publisher):
        self.ws = ws
        self.factory = factory
        self.jobs: dict[str, dict] = {}
        self._lock = threading.Lock()
        self.on_usage: Callable[[str, dict], None] = lambda episode_id, usage: None

    # ---- files
    def path(self, ep: Episode) -> Path:
        return ep.dir / PUBLISH_FILE

    def notes_path(self, episode_id: str) -> Path:
        return inside(self.ws.root, "exports", episode_id, "publish", "notes.md")

    def load(self, ep: Episode) -> dict | None:
        p = self.path(ep)
        if not p.is_file():
            return None
        d = read_json(p)
        if d.get("schema") != PUBLISH_SCHEMA:
            raise ValueError(f"unsupported publish schema {d.get('schema')}")
        return d

    def save(self, ep: Episode, pack: dict) -> None:
        pack["markdown"] = untable(pack["markdown"])
        atomic_write_json(self.path(ep), pack, protected=tuple(Path(m.path) for m in ep.media.values()))
        notes = self.notes_path(ep.id)
        notes.parent.mkdir(parents=True, exist_ok=True)
        tmp = notes.with_name(notes.name + ".tmp")
        tmp.write_text(pack["markdown"], encoding="utf-8")
        os.replace(tmp, notes)

    # ---- generation
    def status(self, episode_id: str) -> dict | None:
        with self._lock:
            j = self.jobs.get(episode_id)
            return dict(j) if j else None

    def start(self, ep: Episode, wait: bool = False) -> dict:
        job = {"state": "running", "stage": tr("读成品转写"), "started": time.time(), "finished": None, "error": None}
        with self._lock:
            if (self.jobs.get(ep.id) or {}).get("state") == "running":
                raise PublishBusy(tr("这一集的发布资料正在生成"))
            self.jobs[ep.id] = job

        def stage(s: str) -> None:
            with self._lock:
                job["stage"] = s

        def run() -> None:
            try:
                self.generate(ep, stage)
                with self._lock:
                    job.update(state="done", stage=tr("完成"), finished=time.time())
            except Exception as e:     # noqa: BLE001 - surfaced to the UI
                if not isinstance(e, PublishError):
                    traceback.print_exc()
                with self._lock:
                    job.update(state="error", finished=time.time(), error=str(e) or type(e).__name__)

        if wait:
            run()
        else:
            threading.Thread(target=run, name=f"publish-{ep.id}", daemon=True).start()
        return self.status(ep.id)

    def generate(self, ep: Episode, stage: Callable[[str], None] = lambda s: None) -> dict:
        segs = segments(ep)
        if not segs:
            raise PublishError(tr("这一集没有转写，写不了 show notes"))
        music = music_info(self.ws, ep)
        names = load_names(self.ws)
        with ep.lock:
            version = ep.version_key()
            duration = music.to_final(ep.timeline_for(ep.enabled).length / ep.sr)
        writer = self.factory()
        stage(tr("LACUNA 在写标题和 show notes") if writer.name == "claude" else tr("生成草稿（AI 没接上）"))
        out = writer.write(ep, segs, music, names, duration)
        if out.usage:
            self.on_usage(ep.id, out.usage)
        draft, notes = clean(out.data, segs)
        if not draft["sections"]:
            raise PublishError(tr("时间轴是空的（引用的段落都对不上），请再生成一次"))
        pack = {"schema": PUBLISH_SCHEMA, "episode": ep.id,
                "generated_at": now_iso(),
                "adapter": out.adapter, "usage": out.usage, "notes": out.notes + notes,
                "draft": draft, "edited": False}
        with ep.lock:
            if ep.version_key() != version:
                pack["notes"].append(tr("生成期间剪辑有变化，时间已按最新剪辑重新对过。"))
            self._layout(ep, pack, music)
            self.save(ep, pack)
        return pack

    # ---- local changes
    def retime(self, ep: Episode) -> dict:
        """Re-place every entry on the current cut (+ current music); keeps Leon's wording."""
        with ep.lock:
            pack = self._need(ep)
            music = music_info(self.ws, ep)
            old_times, old_music = pack["times"], pack.get("music")
            self._layout(ep, pack, music, keep_text=pack["edited"])
            if pack["edited"]:
                pack["markdown"] = retime_markdown(pack["markdown"], old_times, pack["times"])
                if music.credits != old_music:
                    pack["markdown"] = _replace_bgm(pack["markdown"], music.credits)
            self.save(ep, pack)
            return pack

    def edit(self, ep: Episode, markdown: str | None = None, title: str | None = None) -> dict:
        """Save Leon's Markdown (None with no title = back to the generated text) or switch the title."""
        with ep.lock:
            pack = self._need(ep)
            d = pack["draft"]
            if title is not None:
                title = title.strip()[:200]
                if title and title != d["title"]:
                    if title in d["alt_titles"]:
                        d["alt_titles"].remove(title)
                    if d["title"]:
                        d["alt_titles"].insert(0, d["title"])
                    d["title"] = title
                    if pack["edited"]:
                        pack["markdown"] = re.sub(r"^# .*$", f"# {title}", pack["markdown"], count=1, flags=re.M)
            if markdown is not None:
                pack["markdown"], pack["edited"] = markdown, True
            elif title is None or not pack["edited"]:
                self._rerender(ep, pack)
            self.save(ep, pack)
            return pack

    def name(self, ep: Episode, heard: str, action: str) -> dict:
        """Accept (fix everywhere + remember for later episodes) or ignore a suspected misheard name."""
        with ep.lock:
            pack = self._need(ep)
            n = next((n for n in pack["draft"]["names"] if n["heard"] == heard), None)
            if n is None:
                raise KeyError(heard)
            if action == "apply":
                fix = [{"wrong": n["heard"], "right": n["suggested"]}]
                d = pack["draft"]
                for k in ("title", "blurb", "intro"):
                    d[k] = apply_names(d[k], fix)
                d["alt_titles"] = [apply_names(t, fix) for t in d["alt_titles"]]
                for sec in d["sections"]:
                    sec["heading"] = apply_names(sec["heading"], fix)
                    for e in sec["entries"]:
                        e["text"] = apply_names(e["text"], fix)
                for f in d["films"]:
                    f["name"], f["note"] = apply_names(f["name"], fix), apply_names(f["note"], fix)
                d["shows"] = [apply_names(t, fix) for t in d["shows"]]
                d["things"] = [apply_names(t, fix) for t in d["things"]]
                for g in d["glossary"]:
                    g["term"], g["meaning"] = apply_names(g["term"], fix), apply_names(g["meaning"], fix)
                pack["markdown"] = apply_names(pack["markdown"], fix)
                self._layout(ep, pack, music_info(self.ws, ep), keep_text=True)
                add_name(self.ws, n["heard"], n["suggested"])
                n["state"] = "applied"
            else:
                n["state"] = "ignored"
            self.save(ep, pack)
            return pack

    def _need(self, ep: Episode) -> dict:
        pack = self.load(ep)
        if pack is None:
            raise KeyError("no publish pack")
        return pack

    def _rerender(self, ep: Episode, pack: dict) -> None:
        pack["edited"] = False
        self._layout(ep, pack, music_info(self.ws, ep))

    def _layout(self, ep: Episode, pack: dict, music: Music, keep_text: bool = False) -> None:
        """Place the draft on the current cut: times, chapters, Markdown (unless Leon's is kept)."""
        rows = timed(ep, pack["draft"], music)["rows"]
        first: dict[int, float] = {}
        for r in rows:
            first.setdefault(r["section"], r["t"])
        pack.update(version=ep.version_key(), music=music.credits, music_inserts=music.inserts, times=[mmss(r["t"]) for r in rows],
                    chapters=[{"t": round(first.get(i, 0.0), 2), "time": mmss(first.get(i, 0.0)),
                               "heading": s["heading"]} for i, s in enumerate(pack["draft"]["sections"])],
                    gone=[r["text"] for r in rows if r["gone"]])
        if not keep_text:
            pack["markdown"] = render_markdown(ep.id, pack["draft"], rows, music.credits)

    # ---- view
    def view(self, ep: Episode) -> dict:
        job = self.status(ep.id)       # before the pack: a job seen finished has its result in the pack read next
        pack = self.load(ep)
        if pack is not None and has_table(pack["markdown"]):      # written before item 26
            with ep.lock:
                pack = self.load(ep)
                self.save(ep, pack)
        out: dict = {"pack": None, "job": job, "notes_path": str(self.notes_path(ep.id))}
        if pack is None:
            return out
        music = music_info(self.ws, ep)
        d = pack["draft"]
        out["pack"] = {
            "title": d["title"], "alt_titles": d["alt_titles"], "blurb": d["blurb"],
            "markdown": pack["markdown"], "edited": pack["edited"], "chapters": pack["chapters"],
            "names": [{k: n[k] for k in ("heard", "suggested", "why", "state")} for n in d["names"]],
            "stale": pack["version"] != ep.version_key() or music.credits != pack.get("music")
                     or ("music_inserts" in pack and music.inserts != pack["music_inserts"]),
            "gone": pack.get("gone", []), "notes": pack.get("notes", []), "adapter": pack["adapter"],
            "usage": pack.get("usage") or {}, "generated_at": pack["generated_at"],
            "library": music.library,
        }
        return out


def _replace_bgm(md: str, credits: list[dict] | None) -> str:
    """Swap the body of the BGM section (up to the next rule / heading) in edited Markdown."""
    m = re.search(r"(## 🎵 本期 BGM\n\n)(.*?)(\n\n---|\n## |\Z)", md, flags=re.S)  # i18n-ignore
    if not m:
        return md
    return md[:m.start(2)] + "\n".join(bgm_lines(credits)) + md[m.end(2):]
