"""Transcript proofreading against the show's own names (decision `transcript-terms`).

The local recognisers (Paraformer / Parakeet via sherpa-onnx) take no hot words, so they write the
show's names as ordinary words that sound alike: 洛城二三事 → 洛城二三世, Leon → 利奥, Pei → 配,
PULSE → "pose". Right after recognition (before the AI first cut and the transcript are built), one
text-only request per chunk of lines asks a model where one of the show's *reference terms* was
mis-heard; it answers {line, wrong, right} triples and this module makes the change itself:

* ``right`` must be one of the terms (show name, hosts, albums, terms from 项目设置, names Leon
  corrected before, Latin names in the episode title); anything else is dropped;
* ``wrong`` must be in that line and cover whole words (never half of an English word);
* only word *text* changes: start / end times stay, a term heard as several words becomes one word
  spanning them, so every edit, cut and the audio are untouched (no words are added).

Names Leon corrected before (``names.json``, publish.py) are applied without asking. Any failure,
timeout or missing key leaves the text as heard, so an import never fails or waits because of this.
An episode imported before can be proofread again from its 文字稿剪辑 card (routes/transcript_fix.py);
the first such pass keeps the original as ``transcript.before_fix.json``. Only text leaves the server.
Off with ``LACUNA_TRANSCRIPT_FIX=off``.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import show
from .editor import PRICES, find_api_key, sdk_installed
from .words import join_words

MODEL = "claude-sonnet-5-5"
TIMEOUT_S = 90.0
CHUNK_CHARS = 6000           # transcript text per request (~1 h of Chinese talk = 3-4 requests)
WORKERS = 4
MAX_TERMS = 300
CHECK_FILE = "term_check.json"     # <episode>/: the glossary its transcript was last proofread with
LINE_GAP_S = 0.6             # same speaker, shorter pause -> same line (as manual.transcript)

SYSTEM = (Path(__file__).resolve().parent / "prompts" / "transcript_fix.txt").read_text(encoding="utf-8").strip()

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["fixes"],
    "properties": {"fixes": {"type": "array", "items": {
        "type": "object",
        "additionalProperties": False,
        "required": ["line", "wrong", "right"],
        "properties": {"line": {"type": "string", "description": "line id, e.g. L0012"},
                       "wrong": {"type": "string", "description": "the mis-heard characters, copied from the line"},
                       "right": {"type": "string", "description": "the term, spelled as in terms"}}}}},
}

_LATIN_ALNUM = re.compile(r"[A-Za-z0-9]")
_TITLE_WORD = re.compile(r"[A-Za-z][A-Za-z0-9'&.]{2,}")


def enabled_by_env() -> bool:
    return os.environ.get("LACUNA_TRANSCRIPT_FIX", "on").strip().lower() not in ("0", "off", "false", "no")


# ---------------------------------------------------------------------------- reference terms

@dataclass
class Glossary:
    terms: list[str] = field(default_factory=list)
    corrections: list[dict] = field(default_factory=list)       # names.json: {"wrong", "right"}
    show: str = ""
    about: str = ""
    title: str = ""

    def allowed(self) -> dict[str, str]:
        """Lower-cased spelling -> the term as written: what ``right`` may be."""
        out: dict[str, str] = {}
        for t in self.terms + [c["right"] for c in self.corrections]:
            out.setdefault(_key(t), t)
        return out


def _key(s: str) -> str:
    return "".join(c.lower() if len(c.lower()) == 1 else c for c in re.sub(r"\s+", "", s))


def glossary_for(root: str | Path, title: str = "", extra: list[str] = ()) -> Glossary:
    """The workspace's reference terms: show name, hosts and 项目设置 terms (show.json), album names,
    names corrected before (names.json), Latin names in the episode title, `extra` and the system terms."""
    from .publish import NAMES_FILE
    from .store import read_json
    root = Path(root)
    profile = show.load(root)
    terms = [profile.get("show_name") or ""] + show.host_names(profile)
    try:            # decision projects-albums
        from .albums import Albums
        from .store import Workspace
        terms += [str(a.get("name") or "") for a in Albums(Workspace(root)).albums() if isinstance(a, dict)]
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    terms += [str(t) for t in profile.get("terms") or []]
    album = (profile.get("publish") or {}).get("album")
    if isinstance(album, str):
        terms.append(album)
    terms += _TITLE_WORD.findall(title or "")
    terms += list(extra)
    from . import system_terms         # the installation's own list (设置, admins), for every project
    terms += system_terms.load(root)
    corrections: list[dict] = []
    try:
        if (root / NAMES_FILE).is_file():
            corrections = [{"wrong": str(n["wrong"]), "right": str(n["right"])}
                           for n in read_json(root / NAMES_FILE).get("names", []) if n.get("wrong") and n.get("right")]
    except (OSError, ValueError, AttributeError, TypeError):
        corrections = []
    seen: dict[str, str] = {}
    for t in terms:
        t = str(t).strip()
        if t and _key(t) not in seen:
            seen[_key(t)] = t
    return Glossary(list(seen.values())[:MAX_TERMS], corrections, str(profile.get("show_name") or ""),
                    str(profile.get("about") or ""), str(title or ""))


def signature(g: Glossary) -> str:
    """Changes when the terms or corrections change: an episode proofread with another one is due again."""
    doc = [sorted(g.allowed()), sorted((c["wrong"], c["right"]) for c in g.corrections)]
    return hashlib.sha1(json.dumps(doc, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def checked(ep_dir: Path) -> str | None:
    try:
        return str(json.loads((Path(ep_dir) / CHECK_FILE).read_text(encoding="utf-8")).get("sig") or "") or None
    except (OSError, ValueError, AttributeError):
        return None


def mark_checked(ep_dir: Path, g: Glossary) -> None:
    from .store import atomic_write_json
    atomic_write_json(Path(ep_dir) / CHECK_FILE, {"sig": signature(g), "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})


# ---------------------------------------------------------------------------- lines and fixes

@dataclass
class Line:
    id: str
    speaker: str
    words: list[dict]         # {"t", "start", "end", ...}; changed in place
    ref: str = ""             # where the words came from ("<tag>:<segment>" for recognised segments)

    @property
    def text(self) -> str:
        return join_words(w["t"] for w in self.words)


def _units(s: str) -> list[str]:
    """How a replacement splits into words: CJK characters one by one, Latin words whole."""
    return [m for m in re.findall(r"[A-Za-z0-9'&.\-]+|\S", s)]


def find_spans(words: list[dict], wrong: str) -> list[tuple[int, int, str, str]]:
    """Every (first word, last word, text before, text after) where `wrong` (spaces and case ignored)
    covers whole words; a match that would split a Latin word is skipped."""
    target = _key(wrong)
    if not target:
        return []
    flat, owner = [], []
    for i, w in enumerate(words):
        s = re.sub(r"\s+", "", w["t"])
        flat.append(s)
        owner += [i] * len(s)
    text = "".join(c.lower() if len(c.lower()) == 1 else c for c in "".join(flat))
    starts = []
    pos = 0
    for s in flat:
        starts.append(pos)
        pos += len(s)
    out, k = [], text.find(target)
    while k >= 0:
        a, b = owner[k], owner[k + len(target) - 1]
        pre = flat[a][:k - starts[a]]
        post = flat[b][k + len(target) - starts[b]:]
        if not (_LATIN_ALNUM.match(pre[-1:] or " ") and _LATIN_ALNUM.match(target[0])) and \
           not (_LATIN_ALNUM.match(post[:1] or " ") and _LATIN_ALNUM.match(target[-1])):
            out.append((a, b, pre, post))
        k = text.find(target, k + len(target))
    return out


def replace(words: list[dict], wrong: str, right: str) -> int:
    """Write `right` where `wrong` was heard (times kept); returns how many places changed."""
    n = 0
    for a, b, pre, post in reversed(find_spans(words, wrong)):
        units = _units(right)
        if b - a + 1 == len(units) and not pre and not post:      # 二三世 → 二三事: word for word
            for i, u in enumerate(units):
                words[a + i] = dict(words[a + i], t=u)
        else:                                                     # 利奥 → Leon: one word over the span
            words[a] = dict(words[a], t=pre + right + post, end=words[b]["end"])
            if "pause_after" in words[b]:
                words[a]["pause_after"] = words[b]["pause_after"]
            del words[a + 1:b + 1]
        n += 1
    return n


def apply(lines: list[Line], fixes: list[dict]) -> list[dict]:
    """Apply checked fixes ({"line", "wrong", "right"}); returns the ones that changed something,
    with the speaker, the line's start and the count."""
    by_id = {ln.id: ln for ln in lines}
    done = []
    for f in fixes:
        ln = by_id.get(f["line"])
        if ln is None or _key(f["wrong"]) == _key(f["right"]):
            continue
        n = replace(ln.words, f["wrong"], f["right"])
        if n:
            done.append({"line": ln.id, "speaker": ln.speaker, "start": round(float(ln.words[0]["start"]), 2) if ln.words else 0.0,
                         "wrong": f["wrong"], "right": f["right"], "count": n})
    return done


def known(lines: list[Line], g: Glossary) -> list[dict]:
    """names.json corrections wherever they occur (no model needed)."""
    out = []
    for c in sorted(g.corrections, key=lambda c: -len(c["wrong"])):
        for ln in lines:
            if find_spans(ln.words, c["wrong"]):
                out.append({"line": ln.id, "wrong": c["wrong"], "right": c["right"]})
    return out


def check(fixes: list[dict], lines: list[Line], g: Glossary) -> list[dict]:
    """Keep only answers that name a reference term and quote whole words of that line."""
    allowed = g.allowed()
    by_id = {ln.id: ln for ln in lines}
    out = []
    for f in fixes:
        try:
            line, wrong, right = str(f["line"]).strip(), str(f["wrong"]).strip(), str(f["right"]).strip()
        except (KeyError, TypeError):
            continue
        term = allowed.get(_key(right))
        ln = by_id.get(line)
        if term is None or ln is None or not wrong or _key(wrong) == _key(term):
            continue
        if len(_key(wrong)) > 3 * len(_key(term)) + 6:          # a whole clause is not a mis-heard name
            continue
        if not find_spans(ln.words, wrong):
            continue
        out.append({"line": line, "wrong": wrong, "right": term})
    return out


def lines_from_asr(asr: dict[str, dict], names: dict[str, str]) -> list[Line]:
    """One line per recognised segment of each track (main recogniser, BPE pieces merged). The words
    are written back by `write_back`."""
    from .features import merge_bpe
    out = []
    for tag, res in asr.items():
        for si, seg in enumerate(res.get("segments", [])):
            words = merge_bpe(seg["par"]["tokens"])
            if words:
                out.append(Line(f"{tag}:{si}", names.get(tag, tag), words))
    out.sort(key=lambda ln: ln.words[0]["start"])
    for i, ln in enumerate(out):
        ln.id, ln.ref = f"L{i + 1:04d}", ln.id
    return out


def write_back(asr: dict[str, dict], lines: list[Line], done: list[dict]) -> None:
    """Corrected words back into the recognised segments; SenseVoice's reading of the same segment
    gets the same fixes where it heard the same words (so the two engines still agree there)."""
    changed = {f["line"] for f in done}
    pairs: dict[str, list[tuple[str, str]]] = {}
    for f in done:
        pairs.setdefault(f["line"], []).append((f["wrong"], f["right"]))
    for ln in lines:
        if ln.id not in changed:
            continue
        tag, si = ln.ref.split(":")
        seg = asr[tag]["segments"][int(si)]
        seg["par"] = dict(seg["par"], tokens=ln.words, text=ln.text)
        sv = [dict(t) for t in seg.get("sv", {}).get("tokens", []) if t.get("t", "").strip()]
        for wrong, right in pairs[ln.id]:
            replace(sv, wrong, right)
        if "sv" in seg:
            seg["sv"] = dict(seg["sv"], tokens=sv, text=join_words(t["t"].strip() for t in sv))


def lines_from_transcript(transcript: dict) -> list[Line]:
    """An episode's transcript ({"tracks": {name: [[start, end, text], ...]}}) as lines of word dicts."""
    out = []
    for name, words in transcript.get("tracks", {}).items():
        run: list[dict] = []
        for s, e, t in sorted(words, key=lambda w: w[0]):
            if run and s - run[-1]["end"] > LINE_GAP_S:
                out.append(Line("", name, run))
                run = []
            run.append({"t": t, "start": s, "end": e})
        if run:
            out.append(Line("", name, run))
    out.sort(key=lambda ln: ln.words[0]["start"])
    for i, ln in enumerate(out):
        ln.id = f"L{i + 1:04d}"
    return out


def transcript_from_lines(transcript: dict, lines: list[Line]) -> dict:
    tracks: dict[str, list] = {name: [] for name in transcript.get("tracks", {})}
    for ln in lines:
        tracks.setdefault(ln.speaker, []).extend([w["start"], w["end"], w["t"]] for w in ln.words)
    for words in tracks.values():
        words.sort(key=lambda w: w[0])
    return {**transcript, "tracks": tracks}


# ---------------------------------------------------------------------------- the model

def chunks(lines: list[Line], limit: int = CHUNK_CHARS) -> list[list[Line]]:
    out: list[list[Line]] = [[]]
    size = 0
    for ln in lines:
        n = len(ln.text) + 12
        if out[-1] and size + n > limit:
            out.append([])
            size = 0
        out[-1].append(ln)
        size += n
    return [c for c in out if c]


def usage_of(resp, seconds: float) -> dict:
    u = getattr(resp, "usage", None)
    tin = (getattr(u, "input_tokens", 0) or 0) + (getattr(u, "cache_creation_input_tokens", 0) or 0)
    cached = getattr(u, "cache_read_input_tokens", 0) or 0
    tout = getattr(u, "output_tokens", 0) or 0
    model = getattr(resp, "model", None) or MODEL
    pin, pout = PRICES.get(model, (2.0, 10.0))
    return {"kind": "transcript_fix", "model": model, "input_tokens": tin + cached, "output_tokens": tout,
            "seconds": round(seconds, 2), "cost_usd": round((tin * pin + cached * pin * 0.1 + tout * pout) / 1e6, 4)}


class TranscriptFixer:
    """`client` can be injected (tests use a fake with ``messages.create``)."""

    model = MODEL

    def __init__(self, api_key: str | None = None, client: Any = None):
        if api_key is None and client is None:
            api_key, _ = find_api_key()
        self.api_key = api_key
        self._client = client

    @property
    def available(self) -> bool:
        return enabled_by_env() and (self._client is not None or (bool(self.api_key) and sdk_installed()))

    @property
    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key, timeout=TIMEOUT_S, max_retries=1)
        return self._client

    def request(self, part: list[Line], g: Glossary) -> dict:
        doc = {"show": g.show, "about": g.about, "terms": g.terms,
               "known_corrections": [f"{c['wrong']} → {c['right']}" for c in g.corrections],
               "episode_title": g.title,
               "lines": [f"{ln.id} {ln.speaker}：{ln.text}" for ln in part]}
        return dict(model=self.model, max_tokens=4000, system=SYSTEM,
                    output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
                    messages=[{"role": "user", "content": json.dumps(doc, ensure_ascii=False)}])

    def _ask(self, part: list[Line], g: Glossary, on_usage: Callable[[dict], None]) -> list[dict] | None:
        """The model's fixes for one chunk; None when it could not answer (asked again next time)."""
        t0 = time.monotonic()
        try:
            resp = self.client.messages.create(**self.request(part, g))
        except Exception:          # noqa: BLE001 - proofreading must never break an import
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

    def propose(self, lines: list[Line], g: Glossary, on_usage: Callable[[dict], None] = lambda u: None) -> list[dict]:
        return self.propose_all(lines, g, on_usage)[0]

    def propose_all(self, lines: list[Line], g: Glossary,
                    on_usage: Callable[[dict], None] = lambda u: None) -> tuple[list[dict], bool]:
        """(checked fixes for `lines`, whether the model answered for every line): names.json corrections
        plus what the model found (if available)."""
        fixes = known(lines, g)
        complete = self.available
        if self.available and g.terms and lines:
            parts = chunks(lines)
            with ThreadPoolExecutor(min(WORKERS, len(parts)), thread_name_prefix="transcript-fix") as pool:
                for answer in pool.map(lambda p: self._ask(p, g, on_usage), parts):
                    if answer is None:
                        complete = False
                        continue
                    fixes += check(answer, lines, g)
        seen, out = set(), []
        for f in fixes:
            k = (f["line"], _key(f["wrong"]), f["right"])
            if k not in seen:
                seen.add(k)
                out.append(f)
        return out, complete

    def fix(self, lines: list[Line], g: Glossary, on_usage: Callable[[dict], None] = lambda u: None) -> list[dict]:
        """Propose and apply; returns the fixes that changed something."""
        return apply(lines, self.propose(lines, g, on_usage))


def summary(done: list[dict]) -> list[dict]:
    """[{"wrong", "right", "count"}] most frequent first, for the interface."""
    acc: dict[tuple[str, str], int] = {}
    for f in done:
        k = (f["wrong"], f["right"])
        acc[k] = acc.get(k, 0) + int(f.get("count", 1))
    return [{"wrong": w, "right": r, "count": n} for (w, r), n in sorted(acc.items(), key=lambda x: -x[1])]
