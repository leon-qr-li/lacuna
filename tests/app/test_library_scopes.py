"""Library scopes (decision library-scopes, 2026-10-18): 公共 (shared by every episode) and 本集
(belongs to given episodes). One file, membership is metadata; deleting an episode for good removes
only the assets that were its alone."""
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lacuna_app import create_app
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.library import Library, available_to
from lacuna_app.store import Workspace

from .synth import AI_EPISODE, EPISODE, make_ai_workspace, make_workspace, write_music

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


@pytest.fixture
def ws(tmp_path) -> Path:
    root = make_ai_workspace(tmp_path / "ws")
    make_workspace(root)                       # two episodes: AI_EPISODE and EPISODE
    return root


@pytest.fixture
def c(ws) -> TestClient:
    return TestClient(create_app(ws, MockEditorAdapter(), web_dist=Path("/nonexistent")))


def upload(c, path, kind="interlude", episode="", note=""):
    params = {"name": Path(path).name, "kind": kind, "note": note}
    if episode:
        params["episode"] = episode
    r = c.post("/api/library/upload", params=params, content=Path(path).read_bytes(),
               headers={"Content-Type": "application/octet-stream"})
    assert r.status_code == 200, r.text
    return r.json()["asset"]


def ids(view) -> set[str]:
    return {a["id"] for a in view["assets"]}


def test_old_index_migrates_to_shared(ws, tmp_path):
    lib = Library(Workspace(ws))
    a = lib.add_file(write_music(tmp_path / "in" / "old.wav", 3.0))
    doc = json.loads(lib.index_path.read_text(encoding="utf-8"))
    for x in doc["assets"]:                    # an index written before scopes existed
        x.pop("shared"), x.pop("episodes")
    lib.index_path.write_text(json.dumps(doc), encoding="utf-8")
    got = lib.asset(a["id"])
    assert got["shared"] is True and got["episodes"] == []
    assert available_to(got, EPISODE) and available_to(got, AI_EPISODE)
    # odd values are made safe: not shared and in no episode would be lost, so it is shared
    doc["assets"][0].update(shared=False, episodes="nope")
    lib.index_path.write_text(json.dumps(doc), encoding="utf-8")
    assert lib.asset(a["id"])["shared"] is True


def test_upload_to_shared_or_episode_and_filter(c, tmp_path):
    shared = upload(c, write_music(tmp_path / "in" / "shared.wav", 3.0))
    mine = upload(c, write_music(tmp_path / "in" / "mine.wav", 4.0), episode=EPISODE)
    assert shared["shared"] is True and shared["episodes"] == []
    assert mine["shared"] is False and mine["episodes"] == [EPISODE]

    full = c.get("/api/library").json()
    assert ids(full) == {shared["id"], mine["id"]}
    assert {e["id"] for e in full["episodes"]} == {EPISODE, AI_EPISODE}
    assert all(e["title"] for e in full["episodes"])
    # the music page of each episode: shared + its own
    assert ids(c.get("/api/library", params={"episode": EPISODE}).json()) == {shared["id"], mine["id"]}
    assert ids(c.get("/api/library", params={"episode": AI_EPISODE}).json()) == {shared["id"]}
    assert c.get("/api/library", params={"episode": "nope"}).status_code == 404
    assert upload_status(c, tmp_path, "nope") == 404


def upload_status(c, tmp_path, episode):
    p = write_music(tmp_path / "in" / f"x_{episode}.wav", 2.5)
    return c.post("/api/library/upload", params={"name": p.name, "kind": "other", "episode": episode},
                  content=p.read_bytes(), headers={"Content-Type": "application/octet-stream"}).status_code


def test_same_file_added_again_joins_where_it_was_added(c, tmp_path):
    src = write_music(tmp_path / "in" / "twice.wav", 3.0)
    a = upload(c, src, episode=EPISODE)
    b = upload(c, src, episode=AI_EPISODE)       # stored once, now in both episodes
    assert a["id"] == b["id"] and b["episodes"] == [EPISODE, AI_EPISODE] and not b["shared"]
    assert len(c.get("/api/library").json()["assets"]) == 1
    s = upload(c, src)                            # added to 公共: shared
    assert s["shared"] is True and s["episodes"] == []


def test_move_share_add(c, tmp_path):
    a = upload(c, write_music(tmp_path / "in" / "a.wav", 3.0))
    c.patch(f"/api/library/assets/{a['id']}", json={"credit": {"title": "Theme", "film": "奥德赛"}})
    scope = lambda body: c.post(f"/api/library/assets/{a['id']}/scope", json=body)  # noqa: E731

    r = scope({"action": "move", "episode": EPISODE}).json()["asset"]
    assert r["shared"] is False and r["episodes"] == [EPISODE]
    assert a["id"] not in ids(c.get("/api/library", params={"episode": AI_EPISODE}).json())
    # credits stay with the asset across scope changes
    assert r["credit"]["title"] == "Theme" and r["credit_line"] == "《奥德赛》原声 — “Theme”"

    r = scope({"action": "add", "episode": AI_EPISODE}).json()["asset"]
    assert r["episodes"] == [EPISODE, AI_EPISODE] and not r["shared"]
    assert a["id"] in ids(c.get("/api/library", params={"episode": AI_EPISODE}).json())
    r = scope({"action": "add", "episode": AI_EPISODE}).json()["asset"]
    assert r["episodes"] == [EPISODE, AI_EPISODE]                        # no duplicates

    r = scope({"action": "move", "episode": AI_EPISODE}).json()["asset"]
    assert r["episodes"] == [AI_EPISODE]

    r = scope({"action": "share"}).json()["asset"]
    assert r["shared"] is True and r["episodes"] == [] and r["credit"]["status"] == "confirmed"

    assert scope({"action": "move"}).status_code == 422
    assert scope({"action": "move", "episode": "nope"}).status_code == 404
    assert scope({"action": "move", "episode": "../x"}).status_code == 400
    assert scope({"action": "explode", "episode": EPISODE}).status_code == 422
    assert c.post("/api/library/assets/a_000/scope", json={"action": "share"}).status_code == 404


def test_music_page_only_takes_assets_of_this_episode(c, tmp_path):
    a = upload(c, write_music(tmp_path / "in" / "only.wav", 3.0), episode=AI_EPISODE)
    r = c.post(f"/api/episodes/{EPISODE}/music", json={"asset_id": a["id"], "role": "intro"})
    assert r.status_code == 422
    r = c.post(f"/api/episodes/{AI_EPISODE}/music", json={"asset_id": a["id"], "role": "intro"})
    assert r.status_code == 200, r.text
    # moved away later: the placement made while it was there keeps working (and its credit)
    c.post(f"/api/library/assets/{a['id']}/scope", json={"action": "move", "episode": EPISODE})
    m = c.get(f"/api/episodes/{AI_EPISODE}/music").json()
    assert len(m["placements"]) == 1 and not m["placements"][0]["missing"]
    assert m["credits"] and m["credits"][0]["credit_line"] == "only"


def test_auto_place_only_offers_this_episodes_assets(ws, tmp_path):
    from lacuna_app.episode import Episode
    from lacuna_app.music import EpisodeMusic
    from lacuna_app.music_assist import auto_place, context
    w = Workspace(ws)
    lib = Library(w)
    other = lib.add_file(write_music(tmp_path / "in" / "other_intro.wav", 3.0), "intro", episode=AI_EPISODE)
    m = EpisodeMusic(w, Episode(w, EPISODE), lib)
    out = auto_place(m)
    assert not any(p["asset_id"] == other["id"] for p in ((out.get("draft") or {}).get("placements") or []))
    assert other["id"] not in {x["asset_id"] for x in context(m, "")["library"]}
    lib.make_shared(other["id"])
    out = auto_place(m)
    assert any(p["asset_id"] == other["id"] for p in out["draft"]["placements"])


def delete_episode(c, eid):
    assert c.post(f"/api/episodes/{eid}/archive").status_code == 200
    r = c.delete(f"/api/episodes/{eid}")
    assert r.status_code == 200, r.text
    return r.json()


def test_archive_leaves_assets_and_delete_removes_only_its_own(ws, c, tmp_path):
    only = upload(c, write_music(tmp_path / "in" / "only.wav", 3.0), episode=AI_EPISODE)
    both = upload(c, write_music(tmp_path / "in" / "both.wav", 3.5), episode=AI_EPISODE)
    c.post(f"/api/library/assets/{both['id']}/scope", json={"action": "add", "episode": EPISODE})
    shared = upload(c, write_music(tmp_path / "in" / "shared.wav", 4.0))
    other = upload(c, write_music(tmp_path / "in" / "other.wav", 4.5), episode=EPISODE)
    lib = Library(Workspace(ws))
    only_path = lib.path_of(lib.asset(only["id"]))
    learning = ws / "learning"
    learning.mkdir(exist_ok=True)
    (learning / "keep.txt").write_text("habits", encoding="utf-8")

    assert c.post(f"/api/episodes/{AI_EPISODE}/archive").status_code == 200
    assert len(c.get("/api/library").json()["assets"]) == 4          # archiving touches no asset
    assert c.post(f"/api/episodes/{AI_EPISODE}/restore").status_code == 200

    out = delete_episode(c, AI_EPISODE)
    assert out["assets"] == ["only.wav"]          # names, for the notice on the 已归档 page
    left = {a["id"]: a for a in c.get("/api/library").json()["assets"]}
    assert set(left) == {both["id"], shared["id"], other["id"]}
    assert left[both["id"]]["episodes"] == [EPISODE] and left[shared["id"]]["shared"]
    assert left[other["id"]]["episodes"] == [EPISODE]
    # removed the library's usual way: the file is in _removed/, not deleted
    assert not only_path.exists() and (ws / "library" / "_removed" / only_path.name).is_file()
    assert (learning / "keep.txt").read_text(encoding="utf-8") == "habits"


def test_delete_keeps_an_asset_another_episode_still_plays(ws, c, tmp_path):
    a = upload(c, write_music(tmp_path / "in" / "used.wav", 3.0))
    assert c.post(f"/api/episodes/{EPISODE}/music", json={"asset_id": a["id"], "role": "intro"}).status_code == 200
    r = c.post(f"/api/library/assets/{a['id']}/scope", json={"action": "move", "episode": AI_EPISODE}).json()
    # moving it doesn't take it from the episode whose music already plays it
    assert r["asset"]["episodes"] == [AI_EPISODE, EPISODE] and "已经用了它" in r["message"]
    pid = c.get(f"/api/episodes/{EPISODE}/music").json()["placements"][0]["id"]
    assert c.patch(f"/api/episodes/{EPISODE}/music/{pid}", json={"asset_id": a["id"], "gain_db": -2}).status_code == 200
    rule = upload(c, write_music(tmp_path / "in" / "series.wav", 3.5), kind="intro", episode=AI_EPISODE)
    Library(Workspace(ws)).save_series("洛城二三事", {"asset_id": rule["id"]}, None)

    out = delete_episode(c, AI_EPISODE)
    assert out["assets"] == []
    left = {x["id"]: x for x in c.get("/api/library").json()["assets"]}
    assert left[a["id"]]["episodes"] == [EPISODE] and not left[a["id"]]["shared"]   # placement never breaks
    assert left[rule["id"]]["shared"] is True                                       # the series rule's intro
    m = c.get(f"/api/episodes/{EPISODE}/music").json()
    assert len(m["placements"]) == 1 and not m["placements"][0]["missing"]


def test_drop_episode_without_assets_is_a_no_op(ws):
    lib = Library(Workspace(ws))
    assert lib.drop_episode(EPISODE) == {"removed": [], "kept": [], "names": []}
    assert not lib.index_path.exists()
