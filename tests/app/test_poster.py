"""Phase 10 cover: Claude's SVG (fake client) per direction, sanitizing, local rendering with the
bundled font, revisions from one sentence, the 3000 px cover files, API."""
import io
import json
import time
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from lacuna_app import Episode, Workspace, create_app
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.poster import (COVER_PX, DIRECTIONS, MAX_ROUNDS, PREVIEW_PX, TOOL, ClaudeDesigner, PosterError, Posters,
                               brief_context, render_png, sanitize)
from lacuna_app.publish import ClaudePublisher, Publisher

from .fake_claude import FakePosterAnthropic, FakePublishAnthropic, poster_svg
from .synth import EPISODE, make_workspace

EP = f"/api/episodes/{EPISODE}"


@pytest.fixture
def ws(tmp_path):
    return Workspace(make_workspace(tmp_path / "ws"))


@pytest.fixture
def ep(ws):
    e = Episode(ws, EPISODE)
    yield e
    e.close()


@pytest.fixture
def pub(ws):
    return Publisher(ws, lambda: ClaudePublisher(client=FakePublishAnthropic()))


@pytest.fixture
def packed(ep, pub):
    assert pub.start(ep, wait=True)["state"] == "done"
    return ep


def posters_with(ws, pub, fake) -> Posters:
    return Posters(ws, pub, lambda: ClaudeDesigner(client=fake))


def png_size(data: bytes) -> tuple[int, int]:
    return Image.open(io.BytesIO(data)).size


# ---------------------------------------------------------------------------- SVG safety

def test_tool_is_strict_and_closed():
    s = TOOL["input_schema"]
    assert TOOL["strict"] is True and s["additionalProperties"] is False
    assert set(s["required"]) == set(s["properties"]) == {"name", "concept", "svg"}


def test_sanitize_removes_anything_reaching_outside_the_file():
    evil = ('<script>alert(1)</script><image href="file:///C:/Users/leon/secret.png" width="10" height="10"/>'
            '<foreignObject><div xmlns="http://www.w3.org/1999/xhtml">x</div></foreignObject>'
            '<use href="https://example.org/a.svg#x"/><use href="#ok"/>'
            '<rect id="ok" width="5" height="5" onload="evil()" fill="url(#g)"/>'
            '<rect width="5" height="5" style="fill:url(https://example.org/x)"/>'
            '<style>@import url(https://example.org/x.css);</style><style>.a{fill:url(#g)}</style>'
            '<a href="https://example.org"><circle r="3"/></a>'
            '<text x="10" y="10">洛城二三事</text><text x="10" y="20">EP 002</text><!-- note -->')
    svg, notes = sanitize(poster_svg("#000", extra=evil))
    for bad in ("script", "image", "foreignObject", "example.org", "onload", "@import", "<a ", "洛城", "note"):
        assert bad not in svg, bad
    assert 'href="#ok"' in svg and 'fill="url(#g)"' in svg and ".a{fill:url(#g)}" in svg
    assert "EP 002" in svg and "TWO FILMS" in svg
    assert notes == ["LACUNA 在海报上写了中文，已经去掉（只用英文）。"]
    assert render_png(svg, 200)        # still a valid SVG


@pytest.mark.parametrize("svg,msg", [
    ("not svg at all", "解析不了"),
    ('<html xmlns="http://www.w3.org/1999/xhtml"></html>', "不是 SVG"),
    ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 800"/>', "不是正方形"),
    ('<svg xmlns="http://www.w3.org/2000/svg"/>', "不是正方形"),
    ('<!DOCTYPE svg [<!ENTITY a "aaaa">]><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"/>', "DOCTYPE"),
    ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">' + "<g/>" * 80_000 + "</svg>", "太大"),
], ids=["garbage", "html", "not-square", "no-viewbox", "doctype", "too-big"])
def test_sanitize_rejects_unusable_svg(svg, msg):
    with pytest.raises(PosterError, match=msg):
        sanitize(svg)


def test_sanitize_fixes_the_size_to_the_design_canvas():
    svg, _ = sanitize('<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300" viewBox="0 0 600 600">'
                      '<rect width="600" height="600"/></svg>')
    assert 'width="1200"' in svg and 'height="1200"' in svg


def test_render_uses_the_bundled_font_at_any_size():
    svg, _ = sanitize('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400"><rect width="400" height="400"/>'
                      '<text x="200" y="220" font-family="Didot, serif" font-size="80" fill="#fff" '
                      'text-anchor="middle">EP 002</text></svg>')
    for px in (PREVIEW_PX, 400):
        png = render_png(svg, px)
        assert png_size(png) == (px, px)
    im = Image.open(io.BytesIO(render_png(svg, 400))).convert("L")
    lit = sum(im.histogram()[129:])
    assert lit > 1500, "the text did not render (no font?)"


# ---------------------------------------------------------------------------- generation

def test_needs_the_publish_pack_first(ws, ep, pub):
    p = posters_with(ws, pub, FakePosterAnthropic())
    with pytest.raises(PosterError, match="发布资料"):
        p.generate(ep, wait=True)
    assert p.view(ep)["has_pack"] is False


def test_needs_claude(ws, packed, pub):
    p = Posters(ws, pub, lambda: types.SimpleNamespace(available=False))
    with pytest.raises(PosterError, match="还没接上 AI"):
        p.generate(packed, wait=True)


def test_generate_draws_one_cover_per_direction(ws, packed, pub):
    fake = FakePosterAnthropic()
    p = posters_with(ws, pub, fake)
    usage = []
    p.on_usage = lambda eid, u: usage.append(eid)
    job = p.generate(packed, wait=True)
    assert job["state"] == "done", job
    assert len(fake.requests) == len(DIRECTIONS) == 4
    req = fake.requests[0]
    # only text goes out: the publish pack's title, blurb, films; examples in the cached system prompt
    sent = req["messages"][0]["content"]
    assert "标题：合成的一期：两部电影" in sent and "《一部电影》：结尾" in sent and "EP 000" in sent
    assert "YOUR DIRECTION FOR THIS VERSION" in sent and "do not drift" in sent
    system = req["system"][0]
    assert system["cache_control"] == {"type": "ephemeral"}
    assert "NO Chinese characters" in system["text"] and "EXAMPLE — OBSESSION" in system["text"]
    assert req["tools"][0]["name"] == "submit_poster"
    heads = sorted(r["messages"][0]["content"].split("YOUR DIRECTION FOR THIS VERSION:\n")[1].split(":")[0]
                   for r in fake.requests)
    assert heads == ["ONE EMBLEM", "PURE GEOMETRY", "SIDE BY SIDE", "YOUR OWN IDEA"]
    assert usage == [EPISODE] * 4

    v = p.view(packed)
    assert [x["id"] for x in v["variants"]] == ["v4", "v3", "v2", "v1"]        # newest first
    assert {x["direction"] for x in v["variants"]} == {k for k, _, _ in DIRECTIONS}
    assert {x["direction_label"] for x in v["variants"]} == {"一个意象", "并置", "色块与几何", "自由发挥"}
    assert all(x["concept"] and "cost_usd" not in x for x in v["variants"])   # included in the plan: no price shown
    assert v["chosen"] is None and v["cover"] is None and v["errors"] == []
    for x in v["variants"]:
        assert png_size(p.preview(packed, x["id"]).read_bytes()) == (PREVIEW_PX, PREVIEW_PX)
    saved = json.loads((packed.dir / "poster.json").read_text(encoding="utf-8"))
    assert saved["schema"] == 1 and len(saved["variants"]) == 4 and saved["variants"][0]["svg"].startswith("<svg")


def test_one_failed_direction_keeps_the_others(ws, packed, pub):
    p = posters_with(ws, pub, FakePosterAnthropic(fail=("PURE GEOMETRY",)))
    assert p.generate(packed, wait=True)["state"] == "done"
    v = p.view(packed)
    assert len(v["variants"]) == 3 and len(v["errors"]) == 1 and v["errors"][0].startswith("色块与几何：")
    # the next good round clears the error list
    p.factory = lambda: ClaudeDesigner(client=FakePosterAnthropic())
    p.generate(packed, wait=True)
    v = p.view(packed)
    assert len(v["variants"]) == 7 and v["errors"] == []


def test_three_rounds_per_episode_then_none_left(ws, packed, pub):
    p = posters_with(ws, pub, FakePosterAnthropic())
    assert p.view(packed)["rounds_left"] == MAX_ROUNDS == 3
    for left in (2, 1, 0):
        p.generate(packed, wait=True)
        assert p.view(packed)["rounds_left"] == left
    with pytest.raises(PosterError, match="本集海报次数用完"):
        p.generate(packed, wait=True)
    assert len(p.view(packed)["variants"]) == 3 * len(DIRECTIONS)


def test_a_round_that_draws_nothing_is_not_counted(ws, packed, pub):
    p = posters_with(ws, pub, FakePosterAnthropic(fail=tuple(b.split(":")[0] for _, _, b in DIRECTIONS)))
    p.generate(packed, wait=True)
    assert p.view(packed)["rounds_left"] == MAX_ROUNDS


def test_all_failed_is_a_job_error(ws, packed, pub):
    p = posters_with(ws, pub, FakePosterAnthropic(fail=tuple(b.split(":")[0] for _, _, b in DIRECTIONS)))
    job = p.generate(packed, wait=True)
    assert job["state"] == "error" and "调用 AI 服务失败" in job["error"]
    assert p.view(packed)["variants"] == []


def test_chinese_text_from_claude_is_dropped_with_a_note(ws, packed, pub):
    p = posters_with(ws, pub, FakePosterAnthropic(extra='<text x="100" y="100">两部电影</text>'))
    p.generate(packed, ["emblem"], wait=True)
    v = p.view(packed)["variants"][0]
    assert v["notes"] == ["LACUNA 在海报上写了中文，已经去掉（只用英文）。"]


def test_revise_adds_a_new_version_from_one_sentence(ws, packed, pub):
    fake = FakePosterAnthropic()
    p = posters_with(ws, pub, fake)
    p.generate(packed, ["emblem"], wait=True)
    with pytest.raises(PosterError, match="说一句"):
        p.revise(packed, "v1", "   ", wait=True)
    with pytest.raises(KeyError):
        p.revise(packed, "v9", "换成暖色", wait=True)
    assert p.revise(packed, "v1", "换成暖色", wait=True)["state"] == "done"
    sent = fake.requests[-1]["messages"][0]["content"]
    assert "换成暖色" in sent and "#4a0b13" in sent        # Leon's words + the cover being changed
    v = p.view(packed)["variants"][0]
    assert v["id"] == "v2" and v["parent"] == "v1" and v["instruction"] == "换成暖色"
    assert v["direction"] == "revision" and v["direction_label"] == "按你的话改"
    doc = p.load(packed)
    assert "#c0672a" in doc["variants"][1]["svg"] and "#4a0b13" not in doc["variants"][1]["svg"]


def test_choose_renders_the_cover_files(ws, packed, pub):
    p = posters_with(ws, pub, FakePosterAnthropic())
    p.generate(packed, ["emblem", "pairing"], wait=True)
    assert p.choose(packed, "v2", wait=True)["state"] == "done"
    out = ws.root / "exports" / EPISODE / "publish"
    jpg, png = (out / "cover.jpg").read_bytes(), (out / "cover.png").read_bytes()
    assert png_size(png) == png_size(jpg) == (COVER_PX, COVER_PX)
    assert Image.open(io.BytesIO(jpg)).format == "JPEG" and len(jpg) < 2_000_000
    assert (out / "cover.svg").read_text(encoding="utf-8") == p.load(packed)["variants"][1]["svg"]
    v = p.view(packed)
    assert v["chosen"] == "v2" and v["cover"]["jpg"] == str(out / "cover.jpg") and v["cover"]["px"] == 3000
    with pytest.raises(KeyError):
        p.choose(packed, "v7", wait=True)


def test_preview_cache_is_rebuilt_from_the_svg(ws, packed, pub):
    p = posters_with(ws, pub, FakePosterAnthropic())
    p.generate(packed, ["emblem"], wait=True)
    path = p.preview_path(packed, "v1")
    first = path.read_bytes()
    path.unlink()
    assert p.preview(packed, "v1").read_bytes() == first          # deterministic render


def test_context_is_the_publish_pack_text(ws, packed, pub):
    ctx = brief_context("EP002_AI", pub.load(packed))
    assert "EP002" in ctx and '"EP 002"' in ctx and "**" not in ctx and "章节：\n- 暖场" in ctx


# ---------------------------------------------------------------------------- API

def wait_job(client, n=200):
    for _ in range(n):
        d = client.get(f"{EP}/poster").json()
        if not d["job"] or d["job"]["state"] != "running":
            return d
        time.sleep(0.05)
    raise AssertionError("job still running")


def test_poster_api(ws, pub):
    posters = posters_with(ws, pub, FakePosterAnthropic(delay=0.3))
    client = TestClient(create_app(ws.root, MockEditorAdapter(), web_dist=Path("/nonexistent"), publisher=pub,
                                   posters=posters))
    d = client.get(f"{EP}/poster").json()
    assert d["variants"] == [] and d["has_pack"] is False and len(d["directions"]) == 4
    r = client.post(f"{EP}/poster/generate")
    assert r.status_code == 400 and "发布资料" in r.json()["detail"]

    client.post(f"{EP}/publish/generate")
    for _ in range(200):
        if client.get(f"{EP}/publish").json()["job"]["state"] != "running":
            break
        time.sleep(0.05)
    r = client.post(f"{EP}/poster/generate")
    assert r.status_code == 200 and r.json()["job"]["state"] == "running"
    assert client.post(f"{EP}/poster/generate").status_code == 409
    d = wait_job(client)
    assert d["job"]["state"] == "done" and len(d["variants"]) == 4

    r = client.get(f"{EP}/poster/v1.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert png_size(r.content) == (PREVIEW_PX, PREVIEW_PX)
    assert client.get(f"{EP}/poster/v9.png").status_code == 404
    assert client.get(f"{EP}/poster/..%2Fstate.png").status_code == 404

    assert client.post(f"{EP}/poster/v1/revise", json={"instruction": ""}).status_code == 422
    assert client.post(f"{EP}/poster/v9/revise", json={"instruction": "暖一点"}).status_code == 404
    assert client.post(f"{EP}/poster/v1/revise", json={"instruction": "换成暖色"}).status_code == 200
    d = wait_job(client)
    assert d["variants"][0]["id"] == "v5" and d["variants"][0]["parent"] == "v1"

    assert client.post(f"{EP}/poster/v5/choose").status_code == 200
    d = wait_job(client, 600)
    assert d["job"]["state"] == "done" and d["chosen"] == "v5"
    assert Path(d["cover"]["jpg"]).is_file()
    usage = [json.loads(ln) for ln in (ws.root / "ai_usage.jsonl").read_text(encoding="utf-8").splitlines()]
    assert sum(u["kind"] == "poster" for u in usage) == 5
