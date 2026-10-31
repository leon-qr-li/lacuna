"""Episode naming per album (naming.py, Leon 2026-10-31): presets and a custom format, applied when an episode
is imported into the album, and to the episodes already in it only when asked."""
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lacuna_app import create_app, naming
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.store import Workspace

from .fake_claude import FakeFirstCutAnthropic
from .synth import AI_EPISODE, EPISODE, fake_asr, make_ai_workspace, make_workspace, write_recordings

ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


@pytest.mark.parametrize("preset,name,title", [
    ("space", "盗梦空间", "EP012 盗梦空间"),
    ("dot", "盗梦空间", "EP012 · 盗梦空间"),
    ("bar", "盗梦空间", "EP012｜盗梦空间"),
    ("colon", "盗梦空间", "EP012：盗梦空间"),
    ("issue", "盗梦空间", "第12期 盗梦空间"),
    ("name", "盗梦空间", "盗梦空间"),
    ("space", "", "EP012"),
    ("issue", "", "第12期"),
    ("name", "", "EP012"),
])
def test_presets(preset, name, title):
    assert naming.title({"preset": preset}, "EP012", name) == title


def test_custom_format_and_no_format():
    fmt = naming.clean({"preset": "custom", "before": "【", "between": "】", "after": " | 洛城"})
    assert naming.title(fmt, "EP012", "盗梦空间") == "【EP012】盗梦空间 | 洛城"
    assert naming.bare("EP012", "【EP012】盗梦空间 | 洛城", fmt) == "盗梦空间"
    assert naming.clean({"preset": ""}) is None and naming.clean(None) is None
    assert naming.title(None, "EP012", "  随便  起的 ") == "随便 起的"
    with pytest.raises(naming.NamingError):
        naming.clean({"preset": "nope"})
    with pytest.raises(naming.NamingError):
        naming.clean({"preset": "custom", "between": "a\nb"})


@pytest.mark.parametrize("typed", ["EP012 盗梦空间", "EP012 · 盗梦空间", "ep012｜盗梦空间", "EP012-盗梦空间", "第12期 盗梦空间",
                                   "盗梦空间"])
def test_the_name_is_found_in_a_title_typed_by_hand(typed):
    assert naming.bare("EP012", typed) == "盗梦空间"


@pytest.fixture
def ws(tmp_path) -> Path:
    root = make_ai_workspace(tmp_path / "ws")
    make_workspace(root)
    return root


@pytest.fixture
def c(ws) -> TestClient:
    return TestClient(create_app(ws, MockEditorAdapter(), web_dist=Path("/nonexistent")))


@ffmpeg
def test_set_preview_and_rename_existing_episodes(c, ws):
    aid = c.post("/api/albums", json={"name": "港片", "episodes": [EPISODE, AI_EPISODE]}).json()["created"]
    before = {e["id"]: e["title"] for e in c.get("/api/episodes").json()["episodes"]}
    assert c.put(f"/api/albums/{aid}/naming", json={"preset": "bogus"}).status_code == 422
    assert c.put(f"/api/albums/{aid}/naming", json={"preset": "dot"}).json() == {"naming": {"preset": "dot"}}
    assert next(a for a in c.get("/api/albums").json()["albums"] if a["id"] == aid)["naming"] == {"preset": "dot"}
    # setting a format renames nothing by itself
    assert {e["id"]: e["title"] for e in c.get("/api/episodes").json()["episodes"]} == before
    plan = c.post(f"/api/albums/{aid}/naming/preview", json={"preset": "dot"}).json()["renames"]
    assert {r["id"] for r in plan} <= {EPISODE, AI_EPISODE}
    for r in plan:
        assert r["after"] == naming.title({"preset": "dot"}, r["id"], naming.bare(r["id"], before[r["id"]]))
    out = c.post(f"/api/albums/{aid}/naming/apply").json()["renamed"]
    assert out == plan
    after = {e["id"]: e["title"] for e in c.get("/api/episodes").json()["episodes"]}
    for r in plan:
        assert after[r["id"]] == r["after"]
        assert c.get(f"/api/episodes/{r['id']}").json()["title"] == r["after"]
    # done once: nothing more to rename
    assert c.post(f"/api/albums/{aid}/naming/preview", json={"preset": "dot"}).json()["renames"] == []
    # no format: nothing to apply
    assert c.put(f"/api/albums/{aid}/naming", json={"preset": None}).json() == {"naming": None}
    assert c.post(f"/api/albums/{aid}/naming/apply").status_code == 422
    assert c.put("/api/albums/al_nope/naming", json={"preset": "dot"}).status_code == 404


@ffmpeg
def test_import_into_an_album_is_named_by_its_format(tmp_path):
    from lacuna_app.first_cut import ClaudeFirstCut
    from lacuna_app.importer import Importer
    rec = write_recordings(tmp_path / "rec")
    w = Workspace(tmp_path / "ws").ensure()
    imp = Importer(w, first_cut_factory=lambda: ClaudeFirstCut(client=FakeFirstCutAnthropic()), asr_backend=fake_asr)
    c = TestClient(create_app(w.root, MockEditorAdapter(), web_dist=Path("/nonexistent"), importer=imp))
    aid = c.post("/api/albums", json={"name": "港片"}).json()["created"]
    c.put(f"/api/albums/{aid}/naming", json={"preset": "space"})
    tracks = [str(rec["Leon"]), str(rec["Pei"])]
    # typed with another separator: the album's own format wins
    assert c.post("/api/imports", json={"id": "EP002", "title": "EP002 · 奥本海默", "tracks": tracks, "album": aid}).status_code == 200
    t = time.time()
    while (job := c.get("/api/imports/EP002").json()["job"])["state"] in ("queued", "running"):
        assert time.time() - t < 60
        time.sleep(0.05)
    assert job["state"] == "done", job["error"]
    assert c.get("/api/episodes/EP002").json()["title"] == "EP002 奥本海默"
