"""Albums (decision projects-albums, 2026-10-20): an optional group of episodes with its own cover and
default opener / ending (overriding the project's); media can belong to the whole project, one album
or one episode."""
import json
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lacuna_app import create_app
from lacuna_app.albums import Albums
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.library import Library, available_to
from lacuna_app.store import Workspace

from .fake_claude import FakeFirstCutAnthropic
from .synth import AI_EPISODE, EPISODE, fake_asr, make_ai_workspace, make_workspace, write_music, write_recordings

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
       b"\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")


@pytest.fixture
def ws(tmp_path) -> Path:
    root = make_ai_workspace(tmp_path / "ws")
    make_workspace(root)                       # two episodes: AI_EPISODE and EPISODE
    return root


@pytest.fixture
def c(ws) -> TestClient:
    return TestClient(create_app(ws, MockEditorAdapter(), web_dist=Path("/nonexistent")))


def upload(c, path, kind="interlude", **scope):
    params = {"name": Path(path).name, "kind": kind, **scope}
    r = c.post("/api/library/upload", params=params, content=Path(path).read_bytes(),
               headers={"Content-Type": "application/octet-stream"})
    assert r.status_code == 200, r.text
    return r.json()["asset"]


def test_no_albums_by_default(c):
    v = c.get("/api/albums").json()
    assert v == {"albums": [], "episodes": {}, "project": {"intro": None, "outro": None}}


def test_series_rules_become_project_and_album_defaults(ws, tmp_path):
    lib = Library(Workspace(ws))
    a = lib.add_file(write_music(tmp_path / "in" / "theme.wav", 3.0), "intro")
    b = lib.add_file(write_music(tmp_path / "in" / "nineties.wav", 3.0), "intro")
    lib.save_series("九十年代港片", {"asset_id": b["id"], "solo_s": 2.0}, None, default=False)
    lib.save_series("洛城二三事", {"asset_id": a["id"], "solo_s": 4.0}, None)            # the default rule
    doc = Albums(Workspace(ws)).load()
    assert doc["project"]["intro"] == {"asset_id": a["id"], "solo_s": 4.0} and doc["project"]["outro"] is None
    assert [x["name"] for x in doc["albums"]] == ["九十年代港片"] and doc["albums"][0]["intro"]["asset_id"] == b["id"]
    assert (ws / "albums.json").is_file()        # moved once; later reads use the file


def test_create_assign_and_album_overrides_project(c, ws, tmp_path):
    proj = upload(c, write_music(tmp_path / "in" / "proj_intro.wav", 3.0), "intro")
    outro = upload(c, write_music(tmp_path / "in" / "proj_outro.wav", 3.5), "outro")
    mine = upload(c, write_music(tmp_path / "in" / "album_intro.wav", 4.0), "intro")
    assert c.patch("/api/albums/project", json={"intro": proj["id"], "outro": outro["id"]}).status_code == 200
    r = c.post("/api/albums", json={"name": "  九十年代港片 ", "intro": mine["id"], "episodes": [EPISODE]})
    assert r.status_code == 200, r.text
    aid = r.json()["created"]
    album = r.json()["albums"][0]
    assert album["name"] == "九十年代港片" and album["episodes"] == [EPISODE] and album["cover_url"] is None
    assert album["intro"]["name"] == "album_intro.wav" and album["outro"] is None
    al = Albums(Workspace(ws))
    d = al.defaults_for(EPISODE)
    assert d["intro"]["asset_id"] == mine["id"] and d["intro_from"] == "album"           # the album's wins
    assert d["outro"]["asset_id"] == outro["id"] and d["outro_from"] == "project"        # left empty: the project's
    loose = al.defaults_for(AI_EPISODE)
    assert loose["album"] is None and loose["intro"]["asset_id"] == proj["id"]
    # the music page of an album episode offers its defaults with where they come from
    sug = c.get(f"/api/episodes/{EPISODE}/music").json()["series_suggestion"]
    assert sug == {"name": "九十年代港片", "from": "album", "intro": "album_intro.wav", "outro": "proj_outro.wav",
                   "intro_from": "album", "outro_from": "project"}
    m = c.post(f"/api/episodes/{EPISODE}/music/series/apply", json={}).json()
    assert sorted(p["role"] for p in m["placements"]) == ["intro", "outro"]
    # back to the project's opener; rename; bad requests
    v = c.patch(f"/api/albums/{aid}", json={"intro": "", "name": "港片"}).json()
    assert v["albums"][0]["intro"] is None and v["albums"][0]["name"] == "港片"
    assert al.defaults_for(EPISODE)["intro_from"] == "project"
    assert c.post("/api/albums", json={"name": "   "}).status_code == 422
    assert c.post("/api/albums", json={"name": "x", "episodes": ["EP999"]}).status_code == 404
    assert c.patch("/api/albums/al_nope", json={"name": "x"}).status_code == 404
    assert c.patch(f"/api/albums/{aid}", json={"intro": "a_nope"}).status_code == 404


def test_move_episode_between_albums(c):
    a = c.post("/api/albums", json={"name": "A"}).json()["created"]
    b = c.post("/api/albums", json={"name": "B", "episodes": [EPISODE]}).json()["created"]
    v = c.post(f"/api/episodes/{EPISODE}/album", json={"album": a}).json()
    assert v["episodes"] == {EPISODE: a}
    assert {x["id"]: x["episodes"] for x in v["albums"]} == {a: [EPISODE], b: []}
    v = c.post(f"/api/episodes/{EPISODE}/album", json={"album": None}).json()
    assert v["episodes"] == {}
    assert c.post(f"/api/episodes/{EPISODE}/album", json={"album": "al_nope"}).status_code == 404
    assert c.post("/api/episodes/EP999/album", json={"album": a}).status_code == 404


def test_album_media_scope(c, ws, tmp_path):
    aid = c.post("/api/albums", json={"name": "港片", "episodes": [EPISODE]}).json()["created"]
    song = upload(c, write_music(tmp_path / "in" / "neon.wav", 3.0), album=aid)
    assert song["shared"] is False and song["albums"] == [aid] and song["episodes"] == []
    own = upload(c, write_music(tmp_path / "in" / "own.wav", 3.5), episode=EPISODE)
    common = upload(c, write_music(tmp_path / "in" / "common.wav", 4.0))
    assert available_to(song, EPISODE, aid) and not available_to(song, AI_EPISODE, None)
    view = c.get("/api/library", params={"episode": EPISODE}).json()
    groups = {a["name"]: a["group"] for a in view["assets"]}
    assert groups == {"neon.wav": "album", "own.wav": "episode", "common.wav": "project"}
    assert view["album"] == aid and view["albums"] == [{"id": aid, "name": "港片"}]
    other = c.get("/api/library", params={"episode": AI_EPISODE}).json()
    assert {a["name"] for a in other["assets"]} == {"common.wav"}
    # the album's episodes are told apart on the library page
    eps = {e["id"]: e["album"] for e in c.get("/api/library").json()["episodes"]}
    assert eps == {EPISODE: aid, AI_EPISODE: None}
    # change scope: into the album, then the whole project
    r = c.post(f"/api/library/assets/{common['id']}/scope", json={"action": "album", "album": aid}).json()
    assert r["asset"]["albums"] == [aid] and not r["asset"]["shared"]
    r = c.post(f"/api/library/assets/{common['id']}/scope", json={"action": "share"}).json()
    assert r["asset"]["shared"] and r["asset"]["albums"] == []
    assert c.post(f"/api/library/assets/{own['id']}/scope", json={"action": "album", "album": "al_x"}).status_code == 404
    # an episode outside the album whose music already plays it keeps it
    c.post(f"/api/episodes/{AI_EPISODE}/music", json={"asset_id": common["id"], "role": "intro"})
    r = c.post(f"/api/library/assets/{common['id']}/scope", json={"action": "album", "album": aid}).json()
    assert r["asset"]["episodes"] == [AI_EPISODE] and "已经用了它" in r["message"]
    # the same file added again into the album joins it
    again = upload(c, write_music(tmp_path / "in" / "own.wav", 3.5), album=aid)
    assert again["id"] == own["id"] and again["albums"] == [aid] and again["episodes"] == [EPISODE]


def test_delete_album_keeps_episodes_and_media(c, tmp_path):
    aid = c.post("/api/albums", json={"name": "港片", "episodes": [EPISODE]}).json()["created"]
    song = upload(c, write_music(tmp_path / "in" / "neon.wav", 3.0), album=aid)
    v = c.delete(f"/api/albums/{aid}").json()
    assert v["albums"] == [] and v["episodes"] == {} and v["moved"] == [EPISODE]
    left = {a["id"]: a for a in c.get("/api/library").json()["assets"]}
    assert left[song["id"]]["shared"] is True                    # nothing is lost: it belongs to the project now
    assert EPISODE in [e["id"] for e in c.get("/api/episodes").json()["episodes"]]
    assert c.delete(f"/api/albums/{aid}").status_code == 404


def test_cover_upload(c, ws):
    aid = c.post("/api/albums", json={"name": "港片"}).json()["created"]
    r = c.post(f"/api/albums/{aid}/cover", content=PNG, headers={"Content-Type": "image/png"})
    assert r.status_code == 200, r.text
    url = r.json()["albums"][0]["cover_url"]
    got = c.get(url)
    assert got.status_code == 200 and got.content == PNG
    first = list((ws / "albums" / aid).iterdir())
    c.post(f"/api/albums/{aid}/cover", content=PNG, headers={"Content-Type": "image/png"})
    assert len(list((ws / "albums" / aid).iterdir())) == 1 and list((ws / "albums" / aid).iterdir()) != first
    assert c.post(f"/api/albums/{aid}/cover", content=b"GIF89a", headers={"Content-Type": "image/gif"}).status_code == 415
    assert c.post(f"/api/albums/{aid}/cover", content=b"", headers={"Content-Type": "image/png"}).status_code == 422
    c.delete(f"/api/albums/{aid}")
    assert not (ws / "albums" / aid).exists()


def test_save_defaults_from_an_episode(c, tmp_path):
    aid = c.post("/api/albums", json={"name": "港片", "episodes": [EPISODE]}).json()["created"]
    j = upload(c, write_music(tmp_path / "in" / "j.wav", 6.0), "intro")
    c.post(f"/api/episodes/{EPISODE}/music", json={"asset_id": j["id"], "role": "intro", "solo_s": 3})
    assert c.post(f"/api/episodes/{EPISODE}/music/series/save", json={"target": "album"}).status_code == 200
    album = c.get("/api/albums").json()["albums"][0]
    assert album["id"] == aid and album["intro"]["asset_id"] == j["id"]
    assert c.get("/api/albums").json()["project"]["intro"] is None
    assert c.post(f"/api/episodes/{EPISODE}/music/series/save", json={"target": "nope"}).status_code == 422


def test_permanent_delete_forgets_the_album_place(c, ws):
    aid = c.post("/api/albums", json={"name": "港片", "episodes": [AI_EPISODE, EPISODE]}).json()["created"]
    assert c.post(f"/api/episodes/{AI_EPISODE}/archive").status_code == 200
    assert c.request("DELETE", f"/api/episodes/{AI_EPISODE}").status_code == 200
    assert json.loads((ws / "albums.json").read_text(encoding="utf-8"))["episodes"] == {EPISODE: aid}


def test_import_into_an_album_gets_its_opener(tmp_path):
    from lacuna_app.first_cut import ClaudeFirstCut
    from lacuna_app.importer import Importer
    rec = write_recordings(tmp_path / "rec")
    w = Workspace(tmp_path / "ws").ensure()
    imp = Importer(w, first_cut_factory=lambda: ClaudeFirstCut(client=FakeFirstCutAnthropic()), asr_backend=fake_asr)
    c = TestClient(create_app(w.root, MockEditorAdapter(), web_dist=Path("/nonexistent"), importer=imp))
    j = upload(c, write_music(tmp_path / "in" / "j.wav", 4.0), "intro")
    aid = c.post("/api/albums", json={"name": "港片", "intro": j["id"]}).json()["created"]
    tracks = [str(rec["Leon"]), str(rec["Pei"])]
    assert c.post("/api/imports", json={"id": "EP002", "tracks": tracks, "album": "al_nope"}).status_code == 422
    assert c.post("/api/imports", json={"id": "EP002", "tracks": tracks, "album": aid}).status_code == 200
    t = time.time()
    while (job := c.get("/api/imports/EP002").json()["job"])["state"] in ("queued", "running"):
        assert time.time() - t < 60
        time.sleep(0.05)
    assert job["state"] == "done", job["error"]
    assert c.get("/api/albums").json()["episodes"] == {"EP002": aid}
    m = c.get("/api/episodes/EP002/music").json()
    assert [(p["role"], p["asset_id"]) for p in m["placements"]] == [("intro", j["id"])]
    assert m["series_suggestion"] is None
