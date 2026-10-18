"""「喜马拉雅版」 show notes (backlog item 26): the publish pack's Markdown laid out three ways for the
喜马拉雅 description editor, which has only 正文 / 标题, bold, font, image, tag, quote and rule: no
tables, no lists, a single line break is swallowed and pasted text can carry bold along.

* ``parse`` reads the show notes Markdown (generated or edited by Leon, so his wording stays) into
  parts: intro, timeline groups, films, glossary, BGM ...
* each style turns that into a list of nodes (heading / paragraph / bold line / quote / rule /
  image slot); ``to_html`` gives one ``<p>`` per line for a rich paste, ``to_text`` the same with a
  blank line between lines for a plain paste.
* every timeline line starts with its timestamp as plain text ("12:34 ..."), so 喜马拉雅 and
  小宇宙 (synced from it) turn it into a jump link; the timeline is never an image.
* the 「图文」 style has two designed images (title banner, films card), rendered locally from SVG
  with resvg like the cover (D49, no paid image API). The editor can't take them from a paste, so
  the copied text holds a 【插图】 line where Leon inserts the PNG with the editor's image button.
"""
from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass, field
from pathlib import Path

FONTS = Path(__file__).resolve().parent / "fonts"
# Chinese on the images comes from a system font (Windows: 微软雅黑, macOS: 苹方 / 冬青黑体)
CJK = "Microsoft YaHei, PingFang SC, Hiragino Sans GB, Noto Sans CJK SC, Source Han Sans SC, WenQuanYi Zen Hei, sans-serif"
STYLES = ("magazine", "cinema", "cards")
IMAGES = ("banner.png", "films.png")
W = 1200                 # image width (shown at about half that in the editor, sharp on phones)

_T = r"\d{1,2}:\d{2}(?::\d{2})?"
_TIME = re.compile(rf"^(?:\*\*({_T})\*\*|({_T}))\s+(.*)$")
_LEAD = re.compile(r"^[^\w《「（(一-鿿]+")


# ---------------------------------------------------------------------------- Markdown -> parts

@dataclass
class Part:
    heading: str                      # without its emoji
    kind: str                         # timeline | films | things | glossary | bgm | other
    blocks: list[tuple] = field(default_factory=list)   # ("h3", s) ("time", t, s) ("item", s) ("p", s) ("q", s)


@dataclass
class Doc:
    title: str = ""
    byline: str = ""
    intro: list[tuple] = field(default_factory=list)     # ("p", s) ("item", s) ("q", s)
    parts: list[Part] = field(default_factory=list)
    footer: str = ""

    def part(self, kind: str) -> Part | None:
        return next((p for p in self.parts if p.kind == kind), None)


def _kind(heading: str) -> str:
    for key, kind in (("时间轴", "timeline"), ("电影", "films"), ("人和东西", "things"),  # i18n-ignore
                      ("词典", "glossary"), ("梗", "glossary"), ("BGM", "bgm"), ("配乐", "bgm")):  # i18n-ignore
        if key in heading:
            return kind
    return "other"


def parse(md: str) -> Doc:
    doc = Doc()
    lines = md.replace("\r\n", "\n").split("\n")
    para: list[str] = []
    cur: list[tuple] = doc.intro

    def flush() -> None:
        if para:
            cur.append(("p", "".join(para)))
            para.clear()

    for raw in lines:
        ln = raw.strip()
        if not ln or re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", ln):
            flush()
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if m:
            flush()
            level, text = len(m.group(1)), m.group(2).strip()
            if level == 1 and not doc.title and not doc.parts:
                doc.title = text
            elif level <= 2:
                head = _LEAD.sub("", text).strip() or text
                doc.parts.append(Part(head, _kind(head)))
                cur = doc.parts[-1].blocks
            else:
                cur.append(("h3", text))
            continue
        if ln.startswith(">"):
            flush()
            text = ln.lstrip(">").strip()
            if not doc.byline and not doc.parts and not doc.intro:
                doc.byline = text
            elif text:
                cur.append(("q", text))
            continue
        m = re.match(r"^[-*]\s+(.*)$", ln)
        if m:
            flush()
            item = m.group(1).strip()
            t = _TIME.match(item)
            cur.append(("time", t.group(1) or t.group(2), t.group(3).strip()) if t else ("item", item))
            continue
        t = _TIME.match(ln)
        if t and doc.parts and doc.parts[-1].kind == "timeline":
            flush()
            cur.append(("time", t.group(1) or t.group(2), t.group(3).strip()))
            continue
        para.append(ln)
    flush()
    # the closing line in italics is the footer
    for blocks in [doc.parts[-1].blocks if doc.parts else doc.intro]:
        if blocks and blocks[-1][0] == "p" and re.fullmatch(r"\*[^*].*\*", blocks[-1][1]):
            doc.footer = blocks.pop()[1].strip("*").strip()
    return doc


# ---------------------------------------------------------------------------- nodes -> html / text

# ("h", s) heading · ("p", s) line · ("b", s) bold line · ("q", [s]) quote · ("hr", s) rule (s = how
# it reads as plain text) · ("gap",) empty line · ("img", file, alt) image slot

def _inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    return re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"\1", s)        # no italics in the editor


def _plain(s: str) -> str:
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    return re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"\1", s)


def slot_text(file: str) -> str:
    return f"【插图：在这一行插入图片 {file}，然后删掉这一行】"  # i18n-ignore


def to_html(nodes: list[tuple]) -> str:
    out = []
    for n in nodes:
        k = n[0]
        if k == "h":
            out.append(f"<h2>{_inline(n[1])}</h2>")
        elif k == "p":
            out.append(f"<p>{_inline(n[1])}</p>")
        elif k == "b":
            out.append(f"<p><strong>{_inline(_plain(n[1]))}</strong></p>")
        elif k == "q":
            out.append("<blockquote>" + "".join(f"<p>{_inline(x)}</p>" for x in n[1]) + "</blockquote>")
        elif k == "hr":
            out.append("<hr>")
        elif k == "gap":
            out.append("<p><br></p>")
        elif k == "img":
            out.append(f'<p data-img="{html.escape(n[1])}">{html.escape(slot_text(n[1]))}</p>')
    return "\n".join(out)


def to_text(nodes: list[tuple]) -> str:
    """Plain text for the editor: a blank line between lines (a single newline is swallowed)."""
    out: list[str] = []
    for n in nodes:
        k = n[0]
        if k in ("h", "p", "b"):
            out.append(_plain(n[1]))
        elif k == "q":
            out += [f"｜{_plain(x)}" for x in n[1]]
        elif k == "hr":
            out.append(n[1])
        elif k == "img":
            out.append(slot_text(n[1]))
    return "\n\n".join(out) + "\n"


# ---------------------------------------------------------------------------- the three styles

def _intro(doc: Doc, bullet: str) -> list[tuple]:
    out = []
    for b in doc.intro:
        if b[0] == "item":
            out.append(("p", f"{bullet}{b[1]}"))
        elif b[0] == "q":
            out.append(("q", [b[1]]))
        elif b[0] == "p":
            out.append(("p", b[1]))
    return out


def _term(item: str) -> tuple[str, str]:
    """「**网大**：夸人用的」 -> ("网大", "夸人用的"); a ： inside 《》 belongs to the title."""
    m = re.match(r"^\*\*(.+?)\*\*\s*[：:]\s*(.*)$", item)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    depth = 0
    for i, ch in enumerate(item):
        depth += ch == "《"
        depth -= ch == "》" and depth > 0
        if ch == "：" and depth == 0:
            return _plain(item[:i]).strip(), item[i + 1:].strip()
    return _plain(item).strip(), ""


def _other(part: Part, bullet: str) -> list[tuple]:
    out = []
    for b in part.blocks:
        if b[0] == "time":
            out.append(("p", f"{b[1]}  {b[2]}"))
        elif b[0] == "item":
            out.append(("p", f"{bullet}{b[1]}"))
        elif b[0] == "q":
            out.append(("q", [b[1]]))
        elif b[0] == "h3":
            out.append(("b", b[1]))
        else:
            out.append(("p", b[1]))
    return out


def magazine(doc: Doc, label: str) -> list[tuple]:
    """「杂志」: words only, quiet and roomy; headings, quotes and rules do the design."""
    n: list[tuple] = []
    if doc.title:
        n.append(("h", doc.title))
    if doc.byline:
        n.append(("q", [doc.byline]))
    n += _intro(doc, "— ")
    for part in doc.parts:
        n.append(("hr", "—— —— ——"))
        n.append(("h", part.heading))
        if part.kind == "timeline":
            first = True
            for b in part.blocks:
                if b[0] == "h3":
                    if not first:
                        n.append(("gap",))
                    n.append(("b", b[1]))
                    first = False
                elif b[0] == "time":
                    n.append(("p", f"{b[1]}  {b[2]}"))
                else:
                    n += _other(Part("", "other", [b]), "· ")
        elif part.kind == "glossary":
            items = [b for b in part.blocks if b[0] == "item"]
            n.append(("q", [f"**{t}**　{m}" if m else f"**{t}**" for t, m in map(lambda b: _term(b[1]), items)]))
            n += _other(Part("", "other", [b for b in part.blocks if b[0] != "item"]), "· ")
        else:
            n += _other(part, "· ")
    if doc.footer:
        n += [("hr", "—— —— ——"), ("p", doc.footer)]
    return n


CINEMA_LABELS = {"timeline": "TIMELINE", "films": "FILMS", "things": "PEOPLE & THINGS",
                 "glossary": "GLOSSARY", "bgm": "MUSIC", "other": "NOTES"}
RULE = "━━━━━━━━━━━━"


def cinema(doc: Doc, label: str) -> list[tuple]:
    """「片场」: like a film's title cards and end credits; English labels, ▍ and ◆ marks."""
    n: list[tuple] = [("b", f"{label}　·　洛城二三事")]  # i18n-ignore
    if doc.title:
        n.append(("h", doc.title))
    if doc.byline:
        who = doc.byline.split("·")[-1].strip()
        n.append(("p", f"STARRING　{who}"))
    n.append(("hr", RULE))
    n += _intro(doc, "◆ ")
    for part in doc.parts:
        n.append(("hr", RULE))
        n.append(("b", f"▍{CINEMA_LABELS[part.kind]}　{part.heading}"))
        if part.kind == "timeline":
            k = 0
            for b in part.blocks:
                if b[0] == "h3":
                    k += 1
                    n.append(("gap",))
                    n.append(("b", f"PART {k:02d}　{b[1]}"))
                elif b[0] == "time":
                    n.append(("p", f"{b[1]}  ｜  {b[2]}"))
                else:
                    n += _other(Part("", "other", [b]), "◆ ")
        elif part.kind == "films":
            for b in part.blocks:
                if b[0] == "item":
                    name, note = _term(b[1])
                    n.append(("p", f"◆ {name}" + (f"　—　{note}" if note else "")))
                else:
                    n += _other(Part("", "other", [b]), "◆ ")
        elif part.kind == "glossary":
            for b in part.blocks:
                if b[0] == "item":
                    t, m = _term(b[1])
                    n.append(("p", f"「{t}」　{m}"))
                else:
                    n += _other(Part("", "other", [b]), "◆ ")
        elif part.kind == "bgm":
            for b in part.blocks:
                if b[0] == "item":
                    role, song = _term(b[1])
                    n.append(("p", f"♪ {role}　……　{song}" if song else f"♪ {role}"))
                else:
                    n += _other(Part("", "other", [b]), "♪ ")
        else:
            n += _other(part, "◆ ")
    n.append(("hr", RULE))
    if doc.footer:
        n.append(("p", doc.footer))
    n.append(("b", "— FIN —"))
    return n


def cards(doc: Doc, label: str, images: dict[str, str] | None = None) -> list[tuple]:
    """「图文」: a title banner on top and a films card, words in between; quotes for the asides."""
    images = images or {}
    n: list[tuple] = []
    if "banner.png" in images:
        n.append(("img", "banner.png", images["banner.png"]))
    elif doc.title:
        n.append(("h", doc.title))
    n += _intro(doc, "▸ ")
    for part in doc.parts:
        n.append(("hr", "· · ·"))
        if part.kind == "films" and "films.png" in images:
            n.append(("img", "films.png", images["films.png"]))
            names = [_term(b[1])[0] for b in part.blocks if b[0] == "item"]
            n.append(("p", " · ".join(names)))
            n += _other(Part("", "other", [b for b in part.blocks if b[0] not in ("item",)]), "▸ ")
            continue
        n.append(("h", part.heading))
        if part.kind == "timeline":
            for b in part.blocks:
                if b[0] == "h3":
                    n.append(("gap",))
                    n.append(("b", f"【{b[1]}】"))
                elif b[0] == "time":
                    n.append(("p", f"{b[1]}　{b[2]}"))
                else:
                    n += _other(Part("", "other", [b]), "▸ ")
        elif part.kind == "glossary":
            for b in part.blocks:
                if b[0] == "item":
                    t, m = _term(b[1])
                    n.append(("q", [f"**{t}**", m] if m else [f"**{t}**"]))
                else:
                    n += _other(Part("", "other", [b]), "▸ ")
        else:
            n += _other(part, "▸ ")
    if doc.footer:
        n += [("hr", "· · ·"), ("q", [doc.footer])]
    return n


# ---------------------------------------------------------------------------- images (style 「图文」)

def _units(s: str) -> float:
    """Width of a string in em (CJK and full-width = 1, Latin about half)."""
    w = 0.0
    for ch in s:
        o = ord(ch)
        if o >= 0x2E80 or 0xFF00 <= o <= 0xFFEF:
            w += 1.0
        elif ch.isupper() or ch in "MW@%":
            w += 0.68
        elif ch == " ":
            w += 0.3
        else:
            w += 0.55
    return w


def _wrap(s: str, size: float, width: float, max_lines: int = 2) -> list[str]:
    lines, cur = [], ""
    for ch in s:
        if _units(cur + ch) * size > width and cur:
            lines.append(cur)
            cur = ch.lstrip()
        else:
            cur += ch
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:-1] + "…"
    return lines


def _x(s: str) -> str:
    return html.escape(s, quote=True)


_DEFS = """<defs>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0b1022"/><stop offset="1" stop-color="#171c3d"/></linearGradient>
<radialGradient id="glow" cx="0.92" cy="1.05" r="0.75"><stop offset="0" stop-color="#d93366" stop-opacity="0.42"/><stop offset="0.55" stop-color="#8f45f0" stop-opacity="0.10"/><stop offset="1" stop-color="#8f45f0" stop-opacity="0"/></radialGradient>
<linearGradient id="sun" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#df4a22"/><stop offset="0.55" stop-color="#d93366"/><stop offset="1" stop-color="#8f45f0"/></linearGradient>
</defs>"""


def _frame(h: int, body: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" viewBox="0 0 {W} {h}">{_DEFS}'
            f'<rect width="{W}" height="{h}" fill="url(#bg)"/><rect width="{W}" height="{h}" fill="url(#glow)"/>'
            f'<rect x="28" y="28" width="{W - 56}" height="{h - 56}" rx="18" fill="none" stroke="#ffffff" stroke-opacity="0.08"/>'
            f"{body}</svg>")


def banner_svg(doc: Doc, label: str) -> str:
    title = _plain(doc.title) or label
    main, sub = (title.split("：", 1) + [""])[:2] if "：" in title else (title, "")
    h = 600
    body = [f'<text x="96" y="132" font-family="Inter" font-weight="300" font-size="26" letter-spacing="8" fill="#ff8a4c">{_x(label)}</text>',
            f'<text x="{96 + _units(label) * 26 + len(label) * 8 + 26}" y="132" font-family="{CJK}" font-size="26" fill="#c9cbe0">·  洛城二三事</text>',  # i18n-ignore
            '<circle cx="1088" cy="123" r="8" fill="#ff5e3a"/><circle cx="1088" cy="123" r="16" fill="#ff5e3a" fill-opacity="0.22"/>',
            '<text x="1056" y="132" text-anchor="end" font-family="Inter" font-weight="300" font-size="20" letter-spacing="6" fill="#c9cbe0">ON AIR</text>']
    size = 76 if _units(main) * 76 <= W - 192 else 60
    lines = _wrap(main, size, W - 192)
    y = 270 if sub else 300
    for ln in lines:
        body.append(f'<text x="96" y="{y}" font-family="{CJK}" font-weight="700" font-size="{size}" fill="#ffffff">{_x(ln)}</text>')
        y += size * 1.22
    if sub:
        for ln in _wrap(sub, 40, W - 192, 1):
            body.append(f'<text x="96" y="{y + 6}" font-family="{CJK}" font-size="40" fill="#ffc7a8">{_x(ln)}</text>')
            y += 52
    who = (doc.byline.split("·")[-1].strip() if doc.byline else "Leon & Pei").upper()
    body.append(f'<rect x="96" y="{h - 132}" width="132" height="4" rx="2" fill="url(#sun)"/>')
    body.append(f'<text x="96" y="{h - 84}" font-family="Inter" font-weight="300" font-size="24" letter-spacing="10" fill="#9aa0c4">{_x(who)}</text>')
    return _frame(h, "".join(body))


def films_svg(doc: Doc, label: str) -> str | None:
    part = doc.part("films")
    films = [_term(b[1]) for b in part.blocks if b[0] == "item"] if part else []
    if not films:
        return None
    films = films[:30]          # a very long list would make an endless image
    top, row_note, row_plain = 250, 108, 76
    h = top + sum(row_note if note else row_plain for _, note in films) + 120
    body = ['<text x="96" y="124" font-family="Inter" font-weight="300" font-size="22" letter-spacing="10" fill="#ff8a4c">FILMS IN THIS EPISODE</text>',
            f'<text x="96" y="190" font-family="{CJK}" font-weight="700" font-size="48" fill="#ffffff">本期提到的电影</text>',  # i18n-ignore
            '<rect x="96" y="214" width="96" height="4" rx="2" fill="url(#sun)"/>']
    y = top
    for i, (name, note) in enumerate(films):
        name = _plain(name)
        size = min(38.0, (W - 300) / max(_units(name), 1))
        body.append(f'<text x="96" y="{y + 50}" font-family="Inter" font-weight="200" font-size="30" fill="#ff8a4c">{i + 1:02d}</text>')
        body.append(f'<text x="170" y="{y + 50}" font-family="{CJK}" font-size="{size:.1f}" fill="#ffffff">{_x(name)}</text>')
        if note:
            note = _wrap(_plain(note), 26, W - 300, 1)[0]
            body.append(f'<text x="170" y="{y + 88}" font-family="{CJK}" font-size="26" fill="#9aa0c4">{_x(note)}</text>')
        y += row_note if note else row_plain
        if i < len(films) - 1:
            body.append(f'<rect x="170" y="{y - 8}" width="{W - 266}" height="1" fill="#ffffff" fill-opacity="0.08"/>')
    body.append(f'<text x="{W - 96}" y="{h - 70}" text-anchor="end" font-family="{CJK}" font-size="22" fill="#6f7499">《洛城二三事》{_x(label)}</text>')  # i18n-ignore
    return _frame(h, "".join(body))


def render_png(svg: str) -> bytes:
    import resvg_py
    return resvg_py.svg_to_bytes(svg_string=svg, width=W, skip_system_fonts=False, font_dirs=[str(FONTS)],
                                 font_family="Inter", sans_serif_family="Inter")


def write_images(doc: Doc, label: str, folder: Path) -> dict[str, str]:
    """banner.png / films.png in ``folder``; re-rendered only when their SVG changed."""
    out: dict[str, str] = {}
    folder.mkdir(parents=True, exist_ok=True)
    for name, svg in (("banner.png", banner_svg(doc, label)), ("films.png", films_svg(doc, label))):
        png, mark = folder / name, folder / (name + ".sha1")
        if svg is None:
            png.unlink(missing_ok=True)
            mark.unlink(missing_ok=True)
            continue
        sha = hashlib.sha1(svg.encode("utf-8")).hexdigest()
        if not png.is_file() or not mark.is_file() or mark.read_text(encoding="utf-8") != sha:
            tmp = png.with_name(name + ".tmp")
            tmp.write_bytes(render_png(svg))
            tmp.replace(png)
            mark.write_text(sha, encoding="utf-8")
        out[name] = {"banner.png": "标题横幅", "films.png": "本期提到的电影"}[name]  # i18n-ignore
    return out


# ---------------------------------------------------------------------------- all three

def build(markdown: str, label: str, image_dir: Path | None = None) -> dict:
    """{style: {"html", "text", "images": [file ...]}} for the three styles."""
    doc = parse(markdown)
    images = write_images(doc, label, image_dir) if image_dir is not None else {}
    out = {}
    for style, fn in (("magazine", magazine), ("cinema", cinema), ("cards", None)):
        nodes = cards(doc, label, images) if fn is None else fn(doc, label)
        out[style] = {"html": to_html(nodes), "text": to_text(nodes),
                      "images": [x[1] for x in nodes if x[0] == "img"]}
    return out
