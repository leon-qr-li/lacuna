"""The episode's name (episode_name.py, Leon 2026-11-02): rename any time, an album format kept around the
name, and one name everywhere: a rename becomes the publish title, and a title picked on the publish page
(or fixed by the name check) renames the episode."""
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lacuna_app import Episode, Workspace, create_app, episode_name, naming
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.publish import ClaudePublisher, Publisher

from .fake_claude import FakePublishAnthropic
from .synth import EPISODE, make_workspace

ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
EP = f"/api/episodes/{EPISODE}"
AI_TITLES = ["合成的一期：两部电影", "两部电影一个结尾", "那个结尾到底好不好"]


@pytest.fixture
def ws(tmp_path):
    return Workspace(make_workspace(tmp_path / "ws"))


@pytest.fixture
def pub(ws):
    return Publisher(ws, lambda: ClaudePublisher(client=FakePublishAnthropic()))


@pytest.fixture
def c(ws, pub) -> TestClient:
    return TestClient(create_app(ws.root, MockEditorAdapter(), web_dist=Path("/nonexistent"), publisher=pub))


def wait_pack(c):
    c.post(f"{EP}/publish/generate")
    t = time.time()
    while (d := c.get(f"{EP}/publish").json())["job"]["state"] == "running":
        assert time.time() - t < 30
        time.sleep(0.05)
    assert d["job"]["state"] == "done", d["job"]
    return d["pack"]


@pytest.mark.parametrize("fmt,title,name,short", [
    (None, "EP012", "", ""),
    (None, "", "", ""),
    (None, "EP012 盗梦空间", "EP012 盗梦空间", "盗梦空间"),
    (None, "随便起的", "随便起的", "随便起的"),
    ({"preset": "space"}, "EP012", "", ""),
    ({"preset": "space"}, "EP012 盗梦空间", "盗梦空间", "盗梦空间"),
    ({"preset": "issue"}, "第12期", "", ""),
])
def test_name_of_a_title(fmt, title, name, short):
    assert episode_name.name_of("EP012", title, fmt) == name
    assert (naming.bare("EP012", title, fmt) if name else "") == short


def test_rename_view_and_back_to_the_number(c):
    v = c.get(f"{EP}/name").json()
    assert v["named"] and v["name"] == v["title"] == "合成测试集" and v["album"] is None and v["naming"] is None
    v = c.put(f"{EP}/name", json={"name": "  两个  人的电影 "}).json()
    assert v["title"] == v["name"] == "两个 人的电影" and v["named"]
    assert c.get(f"/api/episodes/{EPISODE}").json()["title"] == "两个 人的电影"
    assert next(e for e in c.get("/api/episodes").json()["episodes"] if e["id"] == EPISODE)["title"] == "两个 人的电影"
    v = c.put(f"{EP}/name", json={"name": ""}).json()
    assert v["title"] == EPISODE and not v["named"] and v["short"] == ""
    assert c.put(f"{EP}/name", json={"name": "x" * 201}).status_code == 422
    assert c.put("/api/episodes/nope/name", json={"name": "a"}).status_code == 404


@ffmpeg
def test_in_an_album_with_a_format_only_the_name_changes(c):
    aid = c.post("/api/albums", json={"name": "港片", "episodes": [EPISODE]}).json()["created"]
    c.put(f"/api/albums/{aid}/naming", json={"preset": "dot"})
    v = c.put(f"{EP}/name", json={"name": "盗梦空间"}).json()
    assert v["title"] == f"{EPISODE} · 盗梦空间" and v["name"] == v["short"] == "盗梦空间"
    assert v["album"] == {"id": aid, "name": "港片"} and v["naming"] == {"preset": "dot"}
    v = c.put(f"{EP}/name", json={"name": ""}).json()
    assert v["title"] == EPISODE and not v["named"]


def test_a_named_episode_keeps_its_name_as_the_publish_title(c):
    pack = wait_pack(c)
    assert pack["title"] == "合成测试集"
    assert pack["suggested"] == AI_TITLES                     # LACUNA's titles as written, its own first
    assert pack["alt_titles"] == AI_TITLES
    assert pack["markdown"].startswith("# 合成测试集\n")


def test_an_unnamed_episode_gets_lacunas_title_until_one_is_picked(c):
    c.put(f"{EP}/name", json={"name": ""})
    pack = wait_pack(c)
    assert pack["title"] == AI_TITLES[0] and pack["suggested"] == AI_TITLES
    assert not c.get(f"{EP}/name").json()["named"]
    # picking one on the publish page: the episode is called that everywhere
    v = c.put(f"{EP}/name", json={"name": AI_TITLES[1]}).json()
    assert v["title"] == AI_TITLES[1]
    pack = c.get(f"{EP}/publish").json()["pack"]
    assert pack["title"] == AI_TITLES[1] and pack["suggested"] == AI_TITLES   # the pick list stays as it was
    assert pack["markdown"].startswith(f"# {AI_TITLES[1]}\n")
    # 撤销: back to no name; the pack keeps the title it has
    v = c.put(f"{EP}/name", json={"name": ""}).json()
    assert not v["named"] and c.get(f"{EP}/publish").json()["pack"]["title"] == AI_TITLES[1]


def test_a_title_switched_on_the_publish_pack_renames_the_episode(c):
    wait_pack(c)
    r = c.put(f"{EP}/publish", json={"title": "那个结尾到底好不好"})
    assert r.json()["pack"]["title"] == "那个结尾到底好不好"
    assert c.get(f"{EP}/name").json()["title"] == "那个结尾到底好不好"


def test_the_name_check_fixes_the_episode_name_too(c):
    c.put(f"{EP}/name", json={"name": ""})
    wait_pack(c)
    c.put(f"{EP}/name", json={"name": "两部电影一个结尾"})
    c.post(f"{EP}/publish/names", json={"heard": "结尾", "action": "apply"})
    assert c.get(f"{EP}/publish").json()["pack"]["title"] == "两部电影一个结局"
    assert c.get(f"{EP}/name").json()["title"] == "两部电影一个结局"


def test_rename_without_a_publish_pack(ws, c):
    assert c.put(f"{EP}/name", json={"name": "还没发布"}).json()["title"] == "还没发布"
    assert c.get(f"{EP}/publish").json()["pack"] is None
    e = Episode(ws, EPISODE)
    assert e.meta["title"] == "还没发布"
    e.close()
