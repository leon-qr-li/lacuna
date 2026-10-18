"""「喜马拉雅版」 show notes (backlog item 26): three layouts the 喜马拉雅 editor can take."""
from __future__ import annotations

import io
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from lacuna_app import Episode, Workspace, create_app, ximalaya
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.publish import PROMPTS, ClaudePublisher, Publisher

from .fake_claude import FakePublishAnthropic
from .synth import EPISODE, make_workspace

EP = f"/api/episodes/{EPISODE}"
EXAMPLE = (PROMPTS / "show_notes_example.md").read_text(encoding="utf-8")
TIME = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?\s")


def example_times() -> list[str]:
    return re.findall(r"^- \*\*(\d{1,2}:\d{2}(?::\d{2})?)\*\*", EXAMPLE, flags=re.M)


def test_parse_reads_the_show_notes():
    doc = ximalaya.parse(EXAMPLE)
    assert doc.title == "夏天的四部电影：两个神话，一场 70 毫米热"
    assert doc.byline == "《洛城二三事》EP001 · Leon & Pei"
    assert doc.footer.startswith("《洛城二三事》是 Leon 和 Pei")
    assert [p.kind for p in doc.parts] == ["timeline", "films", "things", "glossary", "bgm"]
    tl = doc.part("timeline")
    assert [b[1] for b in tl.blocks if b[0] == "time"] == example_times()
    assert sum(b[0] == "h3" for b in tl.blocks) == 4
    # "**45:59 间奏**：..." in the BGM list is a credit, not a timeline entry
    assert all(b[0] == "item" for b in doc.part("bgm").blocks)


@pytest.mark.parametrize("style", ximalaya.STYLES)
def test_every_timestamp_starts_its_own_line(style, tmp_path):
    out = ximalaya.build(EXAMPLE, "EP001", tmp_path)[style]
    want = example_times()
    # plain text: a blank line between all lines (喜马拉雅 swallows a single newline)
    lines = out["text"].strip().split("\n\n")
    assert all("\n" not in ln for ln in lines)
    assert [ln.split()[0] for ln in lines if TIME.match(ln)] == want
    # rich text: one <p> per timeline line, the time first and not inside bold or an image
    assert re.findall(r"<p>(\d{1,2}:\d{2}(?::\d{2})?)\s", out["html"]) == want
    for bad in ("<table", "<ul", "<ol", "<li", "<img", "**", "| 片名"):
        assert bad not in out["html"] and bad not in out["text"]
    # nothing is lost on the way: films, glossary, BGM credits and the footer are all there
    for keep in ("《Obsession》", "网大", "Mr. Swift", "45:59", "片尾", "分享给一个也爱看电影的朋友吧"):
        assert keep in out["text"]
    if style != "cards":               # 「图文」 has the directors on the films card
        assert "Curry Barker" in out["text"]
    assert not re.search(r"claude|anthropic", out["html"] + out["text"], re.I)


def test_the_three_styles_differ():
    out = ximalaya.build(EXAMPLE, "EP001")
    assert len({out[s]["text"] for s in ximalaya.STYLES}) == 3
    assert "▍TIMELINE" in out["cinema"]["text"] and "PART 01　暖场：我们的夏天" in out["cinema"]["text"]
    assert "◆ 《蜘蛛侠：英雄重启》Spider-Man: Brand New Day　—　配乐 Michael Giacchino" in out["cinema"]["text"]
    assert "<blockquote>" in out["magazine"]["html"] and "<h2>时间轴</h2>" in out["magazine"]["html"]
    # without an image folder the cards style is words only
    assert out["cards"]["images"] == [] and "【插图" not in out["cards"]["text"]


def test_cards_get_a_banner_and_a_films_card(tmp_path):
    out = ximalaya.build(EXAMPLE, "EP001", tmp_path)["cards"]
    assert out["images"] == ["banner.png", "films.png"]
    assert out["text"].startswith("【插图：在这一行插入图片 banner.png")
    assert '<p data-img="films.png">' in out["html"]
    # the films stay searchable as text next to their card
    assert "《Obsession》 · 《Backrooms》" in out["text"]
    for name in ("banner.png", "films.png"):
        im = Image.open(io.BytesIO((tmp_path / name).read_bytes()))
        assert im.format == "PNG" and im.width == ximalaya.W and im.height >= 600
    # drawn again only when the content changes
    before = (tmp_path / "films.png").stat().st_mtime_ns
    ximalaya.build(EXAMPLE, "EP001", tmp_path)
    assert (tmp_path / "films.png").stat().st_mtime_ns == before
    ximalaya.build(EXAMPLE.replace("Curry Barker", "C. Barker"), "EP001", tmp_path)
    assert (tmp_path / "films.png").stat().st_mtime_ns != before


def test_no_films_no_films_card(tmp_path):
    md = "# 标题\n\n## ⏱ 时间轴\n\n- **00:10** 开场\n\n## 🎵 本期 BGM\n\n- BGM：未设置\n"
    ximalaya.build(EXAMPLE, "EP001", tmp_path)
    out = ximalaya.build(md, "EP002", tmp_path)["cards"]
    assert out["images"] == ["banner.png"] and not (tmp_path / "films.png").exists()
    assert "00:10　开场" in out["text"]


def test_long_title_wraps_inside_the_banner():
    doc = ximalaya.parse("# " + "很长" * 40 + "\n")
    svg = ximalaya.banner_svg(doc, "EP009")
    titles = re.findall(r'font-weight="700" font-size="(\d+)" fill="#ffffff">([^<]*)<', svg)
    assert len(titles) == 2 and titles[-1][1].endswith("…")
    assert all(ximalaya._units(t) * int(size) <= ximalaya.W - 192 + 1 for size, t in titles)


# ---------------------------------------------------------------------------- API

@pytest.fixture
def client(tmp_path):
    ws = Workspace(make_workspace(tmp_path / "ws"))
    pub = Publisher(ws, lambda: ClaudePublisher(client=FakePublishAnthropic()))
    c = TestClient(create_app(ws.root, MockEditorAdapter(), web_dist=Path("/nonexistent"), publisher=pub))
    c.ws, c.pub = ws, pub
    return c


def test_api_without_a_pack(client):
    d = client.get(f"{EP}/publish/ximalaya").json()
    assert d["styles"] is None
    assert client.get(f"{EP}/publish/ximalaya/banner.png").status_code == 404


def test_api_gives_three_styles_and_the_images(client):
    ep = Episode(client.ws, EPISODE)
    client.pub.start(ep, wait=True)
    ep.close()
    d = client.get(f"{EP}/publish/ximalaya").json()
    assert set(d["styles"]) == set(ximalaya.STYLES) and d["stale"] is False and d["notes"] == []
    assert d["dir"].endswith(str(Path("exports") / EPISODE / "publish" / "ximalaya"))
    assert "00:00" in d["styles"]["magazine"]["text"]
    assert d["styles"]["cards"]["images"] == ["banner.png", "films.png"]
    r = client.get(f"{EP}/publish/ximalaya/films.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content[:4] == b"\x89PNG"
    assert client.get(f"{EP}/publish/ximalaya/notes.md").status_code == 404
    # Leon's edits are what gets laid out
    client.put(f"{EP}/publish", json={"markdown": "# 改过的\n\n## ⏱ 时间轴\n\n- **00:05** 我自己写的\n"})
    d = client.get(f"{EP}/publish/ximalaya").json()
    assert "00:05  我自己写的" in d["styles"]["magazine"]["text"]


def test_api_without_images_still_works(client, monkeypatch):
    ep = Episode(client.ws, EPISODE)
    client.pub.start(ep, wait=True)
    ep.close()

    def broken(svg):
        raise RuntimeError("no resvg")
    monkeypatch.setattr(ximalaya, "render_png", broken)
    d = client.get(f"{EP}/publish/ximalaya").json()
    assert d["styles"]["cards"]["images"] == [] and d["notes"]
