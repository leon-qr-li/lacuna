"""Episode cover (phase 10, D38/D48): Claude draws SVG covers, the app renders them locally.

Flow
----
* The episode's ideas come from the phase 9 publish pack (title, blurb, intro, films, chapter
  headings): text only, as for everything sent to the API. No audio, no stills.
* ``generate`` asks Claude for one cover per design direction (``DIRECTIONS``), in parallel, each
  request knowing the other directions so the versions really differ. ``revise`` sends one cover's
  SVG plus Leon's sentence ("换成暖色") and adds the answer as a new version.
* Every SVG goes through ``sanitize`` (no scripts, no external references, no Chinese text) and is
  rendered with resvg using the bundled Inter font only, so the same SVG gives the same PNG on
  Windows, macOS and CI. A 1000 px preview per version; ``choose`` renders the cover at
  3000 × 3000 (square, as 喜马拉雅 requires) as JPEG (for upload) + PNG + the SVG source.

Persistence (D42): ``<episode>/poster.json`` through ``store``; previews in ``<episode>/posters/``
(a cache, re-rendered from the SVG when missing); the chosen cover in
``<workspace>/exports/<episode>/publish/cover.{jpg,png,svg}`` next to the show notes.
"""
from __future__ import annotations

import io
import os
import re
import threading
import time
import traceback
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .editor import ClaudeEditorAdapter, error_message, find_api_key, sdk_installed
from .episode import Episode
from .publish import Publisher, episode_label
from .store import POSTER_FILE, Workspace, atomic_write_json, inside, read_json, now_iso
from . import show
from .i18n import N_, tr

POSTER_SCHEMA = 1
PROMPTS = Path(__file__).resolve().parent / "prompts"
FONTS = Path(__file__).resolve().parent / "fonts"
CANVAS = 1200            # design units of the SVG (viewBox)
PREVIEW_PX = 1000
COVER_PX = 3000          # 喜马拉雅 only demands a square; 3000 also meets Apple Podcasts / Spotify
JPEG_QUALITY = 92        # ~0.3-0.5 MB at 3000 px for these designs
MAX_SVG_BYTES = 300_000
MAX_INSTRUCTION = 500
MAX_ROUNDS = 3        # 「画 4 版」 rounds per episode: included in the plan, so capped instead of priced

# (key, label for Leon, brief for Claude)
DIRECTIONS: list[tuple[str, str, str]] = [
    ("emblem", N_("一个意象"),
     "ONE EMBLEM: a single iconic object or symbol, centred and large, that fuses the episode's main "
     "film with what the hosts made of it (like the OBSESSION and THE ODYSSEY examples)."),
    ("pairing", N_("并置"),
     "SIDE BY SIDE: the films of this episode placed next to each other (grid, diptych, split frame or "
     "mirrored halves), one clear motif each, so the cover shows how the episode connects them "
     "(like the EP001 example)."),
    ("geometry", N_("色块与几何"),
     "PURE GEOMETRY: no literal objects; colour fields, lines, circles, rhythm and one small precise "
     "detail carry the mood of the episode (think Saul Bass, Swiss posters, Kieslowski's Three Colours)."),
    ("free", N_("自由发挥"),
     "YOUR OWN IDEA: the cover you would pick for this episode, as long as it is different from the "
     "three other directions (one emblem / films side by side / pure geometry)."),
]
DIRECTION_LABELS = {k: label for k, label, _ in DIRECTIONS} | {"revision": N_("按你的话改")}

_STR = {"type": "string"}
TOOL = {
    "name": "submit_poster",
    "description": "Submit one episode cover as an SVG document.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["name", "concept", "svg"],
        "properties": {
            "name": {"type": "string", "description": "2-4 English words"},
            "concept": {"type": "string", "description": "1-2 sentences in Simplified Chinese for Leon"},
            "svg": {"type": "string", "description": "the complete SVG document, viewBox 0 0 1200 1200"},
        },
    },
}


class PosterError(RuntimeError):
    pass


class PosterBusy(RuntimeError):
    pass


# ---------------------------------------------------------------------------- SVG safety

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)
_CJK = re.compile(r"[⺀-鿿가-힯豈-﫿＀-￯　-〿]")
_DROP = {"script", "foreignObject", "image", "iframe", "video", "audio", "a", "animate", "animateMotion",
         "animateTransform", "set", "feImage"}
_URL = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.I)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _safe_css(text: str) -> bool:
    if "@import" in text.lower() or "expression(" in text.lower():
        return False
    return all(m.group(2).startswith("#") for m in _URL.finditer(text))


def sanitize(svg: str) -> tuple[str, list[str]]:
    """The SVG with anything that could reach outside the file removed, plus notes for Leon.

    Raises PosterError when it is not a usable SVG at all."""
    notes: list[str] = []
    if len(svg.encode("utf-8")) > MAX_SVG_BYTES:
        raise PosterError(tr("封面文件太大"))
    if re.search(r"<!(DOCTYPE|ENTITY)", svg, re.I):
        raise PosterError(tr("封面里有不允许的 DOCTYPE"))
    try:
        root = ET.fromstring(svg.strip())
    except ET.ParseError as e:
        raise PosterError(tr("封面 SVG 解析不了（{e}）", e=e)) from e
    if root.tag != f"{{{SVG_NS}}}svg":
        raise PosterError(tr("交回的不是 SVG"))
    vb = [float(x) for x in re.split(r"[\s,]+", (root.get("viewBox") or "").strip()) if x]
    if len(vb) != 4 or vb[2] <= 0 or abs(vb[2] - vb[3]) > 0.5:
        raise PosterError(tr("封面不是正方形（viewBox）"))
    root.set("width", str(CANVAS))
    root.set("height", str(CANVAS))

    dropped_cjk = False

    def clean(el: ET.Element) -> None:
        nonlocal dropped_cjk
        for child in list(el):
            if not isinstance(child.tag, str):      # comments / processing instructions
                el.remove(child)
                continue
            name = _local(child.tag)
            if name in _DROP:
                el.remove(child)
                continue
            if name in ("text", "textPath", "tspan") and _CJK.search("".join(child.itertext())):
                el.remove(child)
                dropped_cjk = True
                continue
            if name == "style" and not _safe_css(child.text or ""):
                el.remove(child)
                continue
            clean(child)
        for k in list(el.attrib):
            v = el.attrib[k]
            lk = _local(k)
            if lk.lower().startswith("on"):
                del el.attrib[k]
            elif lk == "href" and not v.startswith("#"):
                del el.attrib[k]
            elif ("url(" in v.lower() or lk == "style") and not _safe_css(v):
                del el.attrib[k]

    clean(root)
    if dropped_cjk:
        notes.append(tr("LACUNA 在封面上写了中文，已经去掉（只用英文）。"))
    return ET.tostring(root, encoding="unicode"), notes


# ---------------------------------------------------------------------------- rendering

def render_png(svg: str, px: int) -> bytes:
    """SVG -> PNG with resvg and the bundled Inter only (no system fonts: same result everywhere)."""
    try:
        import resvg_py
    except ImportError as e:      # pragma: no cover - a dependency of the package
        raise PosterError(tr("缺少 resvg-py（pip install -e . 会装上）")) from e
    try:
        return resvg_py.svg_to_bytes(svg_string=svg, width=px, height=px, skip_system_fonts=True,
                                     font_dirs=[str(FONTS)], font_family="Inter", sans_serif_family="Inter",
                                     serif_family="Inter", monospace_family="Inter")
    except Exception as e:      # noqa: BLE001 - resvg raises ValueError on bad SVG
        raise PosterError(tr("封面渲染失败（{e}）", e=e)) from e


def png_to_jpeg(png: bytes, quality: int = JPEG_QUALITY) -> bytes:
    from PIL import Image
    im = Image.open(io.BytesIO(png)).convert("RGB")
    out = io.BytesIO()
    im.save(out, "JPEG", quality=quality, optimize=True, progressive=True)
    return out.getvalue()


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------- Claude

def _md_plain(s: str) -> str:
    s = re.sub(r"[*_`#>]+", "", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def brief_context(episode_id: str, pack: dict, show_name: str = "洛城二三事") -> str:  # i18n-ignore
    """What Claude knows about the episode: the publish pack's text (phase 9)."""
    d = pack["draft"]
    films = "\n".join(f"- {f['name']}：{f['note']}" for f in d.get("films", [])) or "（没有列出）"  # i18n-ignore
    shows = "、".join(d.get("shows", [])) or "（无）"  # i18n-ignore
    heads = "\n".join(f"- {s['heading']}" for s in d.get("sections", [])) or "（无）"  # i18n-ignore
    return (f"节目：《{show_name}》 {episode_label(episode_id)}（cover text: \"EP {_num(episode_id)}\"）\n"  # i18n-ignore
            f"标题：{d['title']}\n一句话简介：{d.get('blurb', '')}\n\n"  # i18n-ignore
            f"开场介绍：\n{_md_plain(d.get('intro', ''))[:3000]}\n\n"  # i18n-ignore
            f"聊到的电影：\n{films}\n\n聊到的剧集：{shows}\n\n章节：\n{heads}")  # i18n-ignore


def _num(episode_id: str) -> str:
    m = re.match(r"EP(\d+)", episode_id, re.I)
    return m.group(1).zfill(3) if m else "000"


@dataclass
class Design:
    name: str
    concept: str
    svg: str
    usage: dict = field(default_factory=dict)


class ClaudeDesigner:
    """One streamed request per cover; `client` can be injected (tests use a fake)."""

    name = "claude"
    model = ClaudeEditorAdapter.model

    def __init__(self, api_key: str | None = None, client: Any = None, effort: str | None = None):
        if api_key is None and client is None:
            api_key, _ = find_api_key()
        self.api_key = api_key
        self._client = client
        self.show: dict | None = None        # the workspace's show (set by Posters), None = Leon's
        self.effort = effort or os.environ.get("LACUNA_POSTER_EFFORT", "medium")

    @property
    def available(self) -> bool:
        return self._client is not None or (bool(self.api_key) and sdk_installed())

    @property
    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key, timeout=900.0, max_retries=2)
        return self._client

    @staticmethod
    def system(profile: dict | None = None) -> list[dict]:
        ex = "".join(f"\n\nEXAMPLE — {p.stem.upper()} (style reference only):\n{p.read_text(encoding='utf-8')}"
                     for p in sorted((PROMPTS / "poster_examples").glob("*.svg")))
        text = (PROMPTS / "poster_brief.txt").read_text(encoding="utf-8")
        if not show.is_legacy(profile):
            text = show.neutral(text, profile, [
                (text[:text.index("WHAT YOU GET")], poster_intro(profile)),
                ("so Leon has a real choice", "so the editor has a real choice"),
                ("a cover Leon already likes plus one sentence from him", "a cover the editor already likes plus one sentence from them"),
                ("THE STYLE LEON CHOSE (he loved the three examples below;", "THE HOUSE STYLE (the three examples below;"),
                ("Simplified Chinese for Leon", "Simplified Chinese for the editor"),
            ])
        text += ex
        return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]

    def request(self, user: str) -> dict:
        return dict(model=self.model, max_tokens=48000, system=self.system(self.show),
                    output_config={"effort": self.effort}, tools=[TOOL], tool_choice={"type": "auto"},
                    messages=[{"role": "user", "content": user}])

    def _ask(self, user: str) -> Design:
        t0 = time.monotonic()
        try:
            with self.client.beta.messages.stream(betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                                                  **self.request(user)) as s:
                resp = s.get_final_message()
        except Exception as e:      # noqa: BLE001
            raise PosterError(error_message(e, tail="")) from e
        usage = ClaudeEditorAdapter._usage(resp, time.monotonic() - t0)
        if resp.stop_reason == "refusal":
            raise PosterError(tr("LACUNA 没有处理这次请求"))
        for block in resp.content:
            if block.type == "tool_use" and block.name == "submit_poster":
                d = dict(block.input)
                return Design(str(d.get("name", ""))[:60], str(d.get("concept", ""))[:600], str(d.get("svg", "")), usage)
        if resp.stop_reason == "max_tokens":
            raise PosterError(tr("封面太复杂，回答被截断了"))
        raise PosterError(tr("LACUNA 没有交回封面"))

    def design(self, context: str, direction: str) -> Design:
        brief = dict((k, b) for k, _, b in DIRECTIONS)[direction]
        others = "\n".join(f"- {b}" for k, _, b in DIRECTIONS if k != direction)
        return self._ask(f"{context}\n\nYOUR DIRECTION FOR THIS VERSION:\n{brief}\n\n"
                         f"Other versions are being drawn in these directions, so do not drift into them:\n{others}\n\n"
                         "Design the cover and call submit_poster once.")

    def revise(self, context: str, svg: str, instruction: str) -> Design:
        who = "Leon" if show.is_legacy(self.show) else "The editor"
        return self._ask(f"{context}\n\n{who} likes this cover:\n{svg}\n\n"
                         f"{who}'s change request (Chinese, may come from voice dictation):\n{instruction}\n\n"
                         f"Change exactly what {'he asks' if who == 'Leon' else 'they ask'} and keep everything else as it is. "
                         "Call submit_poster once with the full new SVG; name it like the original, "
                         "concept = what you changed, in Chinese.")


def poster_intro(profile: dict) -> str:
    """The cover brief's opening for a show other than Leon's."""
    where = "喜马拉雅 and other podcast apps" if profile["publish"].get("ximalaya") else "podcast apps"  # i18n-ignore
    return (f"LACUNA — episode cover designer for 《{profile['show_name']}》\n\n"
            f"YOU ARE: the art director of 《{profile['show_name']}》, {profile.get('about') or 'a podcast'} "
            f"(hosts: {show.names_en(profile)}). For every episode you design the square cover that goes next "
            f"to the audio on {where}. You draw it yourself, as SVG code. Where the brief says films, read "
            "the works or subjects this episode discusses.\n\n")


def make_designer():
    return ClaudeDesigner()


# ---------------------------------------------------------------------------- posters of a workspace

class Posters:
    """Cover versions per episode: background generation / revision / final render."""

    def __init__(self, ws: Workspace, publisher: Publisher | None = None,
                 factory: Callable[[], Any] = make_designer):
        self.ws = ws
        self.publisher = publisher or Publisher(ws)
        self.factory = factory
        self.jobs: dict[str, dict] = {}
        self._lock = threading.Lock()
        self.on_usage: Callable[[str, dict], None] = lambda episode_id, usage: None

    # ---- files
    def path(self, ep: Episode) -> Path:
        return ep.dir / POSTER_FILE

    def preview_path(self, ep: Episode, vid: str) -> Path:
        return inside(ep.dir, "posters", f"{vid}.png")

    def cover_dir(self, episode_id: str) -> Path:
        return inside(self.ws.root, "exports", episode_id, "publish")

    def load(self, ep: Episode) -> dict:
        p = self.path(ep)
        if not p.is_file():
            return {"schema": POSTER_SCHEMA, "episode": ep.id, "variants": [], "chosen": None, "cover": None}
        d = read_json(p)
        if d.get("schema") != POSTER_SCHEMA:
            raise ValueError(f"unsupported poster schema {d.get('schema')}")
        return d

    def save(self, ep: Episode, doc: dict) -> None:
        atomic_write_json(self.path(ep), doc, protected=tuple(Path(m.path) for m in ep.media.values()))

    def preview(self, ep: Episode, vid: str) -> Path:
        """The 1000 px preview, re-rendered from the stored SVG if the cache file is gone."""
        p = self.preview_path(ep, vid)
        if not p.is_file():
            v = self._variant(self.load(ep), vid)
            _write_bytes(p, render_png(v["svg"], PREVIEW_PX))
        return p

    # ---- jobs
    def status(self, episode_id: str) -> dict | None:
        with self._lock:
            j = self.jobs.get(episode_id)
            return dict(j) if j else None

    def _run(self, ep: Episode, kind: str, stage: str, fn: Callable[[Callable[[str], None]], None],
             wait: bool) -> dict:
        job = {"kind": kind, "state": "running", "stage": stage, "started": time.time(), "finished": None,
               "error": None}
        with self._lock:
            if (self.jobs.get(ep.id) or {}).get("state") == "running":
                raise PosterBusy(tr("这一集的封面正在生成"))
            self.jobs[ep.id] = job

        def set_stage(s: str) -> None:
            with self._lock:
                job["stage"] = s

        def run() -> None:
            try:
                fn(set_stage)
                with self._lock:
                    job.update(state="done", stage=tr("完成"), finished=time.time())
            except Exception as e:     # noqa: BLE001 - surfaced to the UI
                if not isinstance(e, PosterError):
                    traceback.print_exc()
                with self._lock:
                    job.update(state="error", finished=time.time(), error=str(e) or type(e).__name__)

        if wait:
            run()
        else:
            threading.Thread(target=run, name=f"poster-{ep.id}", daemon=True).start()
        return self.status(ep.id)

    def _context(self, ep: Episode) -> str:
        pack = self.publisher.load(ep)
        if pack is None:
            raise PosterError(tr("先在「发布资料」里生成标题和简介，封面按它来设计"))
        return brief_context(ep.id, pack, show.load(self.ws.root)["show_name"])

    def _designer(self):
        d = self.factory()
        if not getattr(d, "available", True):
            raise PosterError(tr("还没接上 AI（没有 AI 密钥），画不了封面"))
        if hasattr(d, "show"):
            d.show = show.load(self.ws.root)
        return d

    def _add(self, ep: Episode, design: Design, direction: str, parent: str | None = None,
             instruction: str | None = None) -> dict:
        """Sanitize + preview-render one design and append it as a new version."""
        svg, notes = sanitize(design.svg)
        png = render_png(svg, PREVIEW_PX)
        with ep.lock:
            doc = self.load(ep)
            n = max((int(v["id"][1:]) for v in doc["variants"]), default=0) + 1
            v = {"id": f"v{n}", "direction": direction, "name": design.name, "concept": design.concept,
                 "svg": svg, "parent": parent, "instruction": instruction, "notes": notes,
                 "usage": design.usage, "created_at": now_iso()}
            _write_bytes(self.preview_path(ep, v["id"]), png)
            doc["variants"].append(v)
            self.save(ep, doc)
        return v

    @staticmethod
    def _rounds_left(ep: Episode, doc: dict) -> int | None:
        """Rounds of 「画 4 版」 this episode has left (None: no cap, the sample's covers cost nothing)."""
        from .sample import sample_designer
        if sample_designer(ep):
            return None
        return max(0, MAX_ROUNDS - int(doc.get("rounds", 0)))

    def generate(self, ep: Episode, directions: list[str] | None = None, wait: bool = False) -> dict:
        keys = directions or [k for k, _, _ in DIRECTIONS]
        if self._rounds_left(ep, self.load(ep)) == 0:
            raise PosterError(tr("本集封面次数用完"))
        context = self._context(ep)
        from .sample import sample_designer
        designer = sample_designer(ep) or self._designer()

        def work(stage: Callable[[str], None]) -> None:
            done, errors = [], []
            stage(tr("LACUNA 在画 {p0} 版封面", p0=len(keys)))

            def one(k: str) -> None:
                try:
                    d = designer.design(context, k)
                    if d.usage:
                        self.on_usage(ep.id, d.usage)
                    self._add(ep, d, k)
                    done.append(k)
                    stage(tr("LACUNA 在画 {p0} 版封面（已完成 {p1}）", p0=len(keys), p1=len(done)))
                except Exception as e:  # noqa: BLE001 - one bad version must not lose the others
                    if not isinstance(e, PosterError):
                        traceback.print_exc()
                    errors.append(tr("{direction}：{error}", direction=tr(DIRECTION_LABELS[k]), error=e))

            with ThreadPoolExecutor(max_workers=len(keys)) as ex:
                list(ex.map(one, keys))
            if not done:
                raise PosterError("；".join(errors) or tr("一版也没画出来"))
            with ep.lock:       # also clears the errors of an earlier round; a round counts once something was drawn
                doc = self.load(ep)
                doc["last_errors"] = errors
                doc["rounds"] = int(doc.get("rounds", 0)) + 1
                self.save(ep, doc)

        return self._run(ep, "generate", tr("准备"), work, wait)

    def revise(self, ep: Episode, vid: str, instruction: str, wait: bool = False) -> dict:
        instruction = instruction.strip()[:MAX_INSTRUCTION]
        if not instruction:
            raise PosterError(tr("说一句想怎么改"))
        base = self._variant(self.load(ep), vid)
        context = self._context(ep)
        designer = self._designer()

        def work(stage: Callable[[str], None]) -> None:
            stage(tr("LACUNA 在按你的话改「{name}」", name=base['name']))
            d = designer.revise(context, base["svg"], instruction)
            if d.usage:
                self.on_usage(ep.id, d.usage)
            self._add(ep, d, "revision", parent=vid, instruction=instruction)

        return self._run(ep, "revise", tr("准备"), work, wait)

    def choose(self, ep: Episode, vid: str, wait: bool = False) -> dict:
        """Render the chosen version at full size into the episode's publish folder."""
        v = self._variant(self.load(ep), vid)

        def work(stage: Callable[[str], None]) -> None:
            stage(tr("渲染 3000×3000 封面"))
            png = render_png(v["svg"], COVER_PX)
            jpg = png_to_jpeg(png)
            out = self.cover_dir(ep.id)
            _write_bytes(out / "cover.png", png)
            _write_bytes(out / "cover.jpg", jpg)
            _write_bytes(out / "cover.svg", v["svg"].encode("utf-8"))
            with ep.lock:
                doc = self.load(ep)
                doc["chosen"] = vid
                doc["cover"] = {"variant": vid, "px": COVER_PX, "folder": str(out),
                                "jpg": str(out / "cover.jpg"), "png": str(out / "cover.png"),
                                "jpg_bytes": len(jpg), "png_bytes": len(png),
                                "rendered_at": now_iso()}
                self.save(ep, doc)

        return self._run(ep, "choose", tr("准备"), work, wait)

    @staticmethod
    def _variant(doc: dict, vid: str) -> dict:
        v = next((v for v in doc["variants"] if v["id"] == vid), None)
        if v is None:
            raise KeyError(vid)
        return v

    # ---- view
    def view(self, ep: Episode) -> dict:
        job = self.status(ep.id)       # before the doc: a job seen finished has its result in the doc read next
        doc = self.load(ep)
        has_pack = self.publisher.load(ep) is not None
        variants = []
        for v in reversed(doc["variants"]):        # newest first
            variants.append({k: v[k] for k in ("id", "direction", "name", "concept", "parent", "instruction",
                                                "notes", "created_at")}
                            | {"direction_label": tr(DIRECTION_LABELS.get(v["direction"], v["direction"]))})
        from .sample import sample_designer
        try:
            available = bool(sample_designer(ep) or getattr(self.factory(), "available", True))
        except Exception:      # noqa: BLE001
            available = False
        return {"variants": variants, "chosen": doc.get("chosen"), "cover": doc.get("cover"), "available": available,
                "errors": doc.get("last_errors", []), "job": job, "has_pack": has_pack,
                "rounds_left": self._rounds_left(ep, doc), "max_rounds": MAX_ROUNDS,
                "directions": [{"key": k, "label": tr(label)} for k, label, _ in DIRECTIONS]}
