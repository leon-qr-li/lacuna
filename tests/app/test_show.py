"""Show profile per workspace (lacuna_app/show.py, routes/show.py): Leon's workspace keeps 《洛城二三事》,
a new workspace starts generic and asks for its show first."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from lacuna_app import create_app, show
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.publish import render_markdown
from tests.app.test_spaces import join, setup
from tests.app.synth import make_workspace


def test_existing_workspace_is_leons_show(tmp_path):
    ws, leon = setup(tmp_path)
    s = leon.get("/api/show").json()
    assert s["needs_setup"] is False and s["legacy"] is True
    assert s["show_name"] == "洛城二三事"
    assert [(h["tag"], h["name"], h["color"]) for h in s["hosts"]] == [("L", "Leon", "blue"), ("P", "Pei", "purple")]
    assert not (ws / show.FILE).exists()           # nothing written just by looking


def test_desktop_folder_without_file_is_leons(tmp_path):
    assert show.load(tmp_path)["show_name"] == "洛城二三事"
    assert show.load(tmp_path)["setup_done"] is True


def test_new_workspace_asks_for_its_show(tmp_path):
    ws, leon = setup(tmp_path)
    beta = join(leon, "beta@example.com")            # gets an empty workspace of their own
    s = beta.get("/api/show").json()
    assert s["needs_setup"] is True and s["legacy"] is False
    assert s["show_name"] == "" and s["hosts"] == []

    r = beta.put("/api/show", json={"show_name": "周末电影院", "hosts": [{"name": "Ana"}, {"name": "Bo"}, {"name": "Cy"}]})
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["needs_setup"] is False
    assert [h["name"] for h in s["hosts"]] == ["Ana", "Bo", "Cy"]
    tags = [h["tag"] for h in s["hosts"]]
    assert len(set(tags)) == 3 and not {"L", "P"} & set(tags)
    assert [h["color"] for h in s["hosts"]] == ["blue", "purple", "teal"]
    # the main workspace is untouched
    assert leon.get("/api/show").json()["show_name"] == "洛城二三事"
    assert not (ws / show.FILE).exists()


def test_tags_stay_with_their_hosts(tmp_path):
    root = tmp_path / "spaces" / "sp_x"
    root.mkdir(parents=True)
    show.write_new(root)
    s = show.save(root, {"show_name": "A", "hosts": [{"name": "Ana"}, {"name": "Bo"}]})
    ana, bo = s["hosts"]
    # rename Ana, drop Bo, add Cy; a made-up tag is not accepted
    s = show.save(root, {"show_name": "A", "hosts": [{"tag": ana["tag"], "name": "Anna"}, {"tag": "Z", "name": "Cy"}]})
    assert s["hosts"][0]["tag"] == ana["tag"] and s["hosts"][0]["name"] == "Anna"
    assert s["hosts"][1]["tag"] not in (ana["tag"], bo["tag"])


@pytest.mark.parametrize("body, msg", [
    ({"show_name": "", "hosts": [{"name": "A"}]}, "名字"),
    ({"show_name": "X", "hosts": []}, "主持人"),
    ({"show_name": "X", "hosts": [{"name": "A"}, {"name": "a"}]}, "同名"),
    ({"show_name": "X", "hosts": [{"name": "A"}, {"name": " "}]}, "名字"),
    ({"show_name": "X", "hosts": [{"name": str(i)} for i in range(5)]}, "每个项目最多 4 位主持人"),
])
def test_refuses_what_would_break_imports(tmp_path, body, msg):
    app = create_app(make_workspace(tmp_path / "ws"), MockEditorAdapter(), web_dist=tmp_path / "none")
    r = TestClient(app).put("/api/show", json=body)
    assert r.status_code == 400 and msg in r.json()["detail"]


def test_leons_profile_survives_a_save_and_stays_legacy(tmp_path):
    ws = make_workspace(tmp_path / "ws")
    c = TestClient(create_app(ws, MockEditorAdapter(), web_dist=tmp_path / "none"))
    s = c.get("/api/show").json()
    s["hosts"][1]["color"] = "pink"
    s["legacy"] = False                              # not something the page can change
    r = c.put("/api/show", json=s).json()
    assert r["legacy"] is True and r["hosts"][1] == {**show.LEGACY["hosts"][1], "color": "pink"}
    assert json.loads((ws / show.FILE).read_text(encoding="utf-8"))["hosts"][0]["tag"] == "L"


def test_corrupt_file_falls_back(tmp_path):
    (tmp_path / show.FILE).write_text("{", encoding="utf-8")
    assert show.load(tmp_path)["show_name"] == "洛城二三事"


def test_show_notes_follow_the_profile():
    draft = {"title": "标题", "intro": "", "sections": [], "films": [], "shows": [], "things": [], "glossary": []}
    legacy = render_markdown("EP008", draft, [], [])
    assert "> 《洛城二三事》" in legacy and "· Leon & Pei" in legacy and "Leon 和 Pei 两个人的电影闲聊" in legacy
    prof = show.normalise({"show_name": "周末电影院", "hosts": [{"name": "Ana"}, {"name": "Bo"}, {"name": "Cy"}]},
                          strict=True, before=show.NEW)
    md = render_markdown("EP008", draft, [], [], prof)
    assert "《周末电影院》" in md and "· Ana, Bo & Cy" in md
    assert "洛城" not in md and "Leon" not in md


def test_byline():
    names = lambda *n: {"hosts": [{"name": x} for x in n]}  # noqa: E731
    assert show.byline(names("A")) == "A"
    assert show.byline(names("A", "B")) == "A & B"
    assert show.byline(names()) == ""


def test_four_hosts_at_most(tmp_path):
    """A project has at most 4 hosts (tracks): 4 save, the page is told the limit."""
    app = create_app(make_workspace(tmp_path / "ws"), MockEditorAdapter(), web_dist=tmp_path / "none")
    c = TestClient(app)
    r = c.put("/api/show", json={"show_name": "X", "hosts": [{"name": n} for n in "ABCD"]})
    assert r.status_code == 200 and len(r.json()["hosts"]) == 4
    assert c.get("/api/show").json()["max_hosts"] == 4
