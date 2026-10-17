"""Only the 3 most recently used episodes stay in memory; the home page list comes from a small
index file instead of loading every episode."""
import gc
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lacuna_app import create_app, episode_index, server
from lacuna_app.editor import MockEditorAdapter

from .synth import make_workspace

IDS = [f"EP00{i}_缓存" for i in range(1, 6)]


@pytest.fixture
def ws(tmp_path):
    root = tmp_path / "ws"
    for eid in IDS:
        make_workspace(root, eid)
    return root


@pytest.fixture
def app(ws):
    return create_app(ws, MockEditorAdapter(), web_dist=Path("/nonexistent"))


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def loads(monkeypatch):
    """Counts Episode objects built from disk."""
    n = {"count": 0}
    real = server.Episode

    def counting(*a, **kw):
        n["count"] += 1
        return real(*a, **kw)
    monkeypatch.setattr(server, "Episode", counting)
    return n


def in_memory(app):
    gc.collect()
    ctx = app.state.ctx
    return set(ctx.episodes), set(ctx._alive.keys())


def test_listing_keeps_nothing_in_memory_and_reuses_the_index(app, client, ws, loads):
    eps = client.get("/api/episodes").json()["episodes"]
    assert [e["id"] for e in eps] == IDS
    assert all(e["pending_review"] == 1 and e["duration"] > 0 for e in eps)
    assert loads["count"] == 5
    assert in_memory(app) == (set(), set())          # listed, then let go
    assert (ws / "episodes" / episode_index.INDEX_FILE).is_file()

    assert client.get("/api/episodes").json()["episodes"] == eps
    assert loads["count"] == 5                       # second listing: index only

    # a fresh app (restart) lists from the index file too
    fresh = TestClient(create_app(ws, MockEditorAdapter(), web_dist=Path("/nonexistent")))
    assert fresh.get("/api/episodes").json()["episodes"] == eps
    assert loads["count"] == 5


def test_only_three_recent_episodes_stay_open(app, client):
    for eid in IDS[:4]:
        assert client.get(f"/api/episodes/{eid}").status_code == 200
    kept, alive = in_memory(app)
    assert list(app.state.ctx.episodes) == IDS[1:4] and kept == alive
    client.get(f"/api/episodes/{IDS[1]}")            # touching one makes it the newest
    assert list(app.state.ctx.episodes) == [IDS[2], IDS[3], IDS[1]]


def test_evicted_episode_reopens_from_disk_with_its_edits(app, client, loads):
    eid = IDS[0]
    s = client.post(f"/api/episodes/{eid}/edits/e003/review", json={"action": "restore"}).json()
    for other in IDS[1:4]:
        client.get(f"/api/episodes/{other}")
    assert eid not in in_memory(app)[1]
    before = loads["count"]
    again = client.get(f"/api/episodes/{eid}").json()
    assert loads["count"] == before + 1
    assert again["duration"] == s["duration"] and again["pending_review"] == 0


def test_episode_held_by_a_job_is_never_loaded_twice(app, client):
    ctx = app.state.ctx
    held = ctx.get(IDS[0])                           # e.g. an export thread still rendering it
    for other in IDS[1:4]:
        ctx.get(other)
    assert IDS[0] not in ctx.episodes
    assert ctx.get(IDS[0]) is held                   # same object: one writer per episode


def test_list_follows_changes(app, client):
    row = lambda: next(e for e in client.get("/api/episodes").json()["episodes"] if e["id"] == IDS[0])
    assert row()["pending_review"] == 1
    client.post(f"/api/episodes/{IDS[0]}/edits/e003/review", json={"action": "keep"})
    assert row()["pending_review"] == 0              # in memory: read live
    for other in IDS[1:4]:
        client.get(f"/api/episodes/{other}")         # evict it
    assert row()["pending_review"] == 0              # from disk, not a stale index row


def test_changed_or_broken_files_rebuild_the_row(app, client, ws, loads):
    client.get("/api/episodes")
    meta = ws / "episodes" / IDS[2] / "episode.json"
    m = json.loads(meta.read_text("utf-8"))
    meta.write_text(json.dumps(m | {"title": "改过的标题"}, ensure_ascii=False), "utf-8")
    n = loads["count"]
    eps = client.get("/api/episodes").json()["episodes"]
    assert eps[2]["title"] == "改过的标题" and loads["count"] == n + 1

    (ws / "episodes" / episode_index.INDEX_FILE).write_text("{not json", "utf-8")
    bak = ws / "episodes" / (episode_index.INDEX_FILE + ".bak")
    bak.unlink(missing_ok=True)
    assert client.get("/api/episodes").json()["episodes"] == eps


def test_broken_episode_is_listed_with_an_error(app, client, ws):
    (ws / "episodes" / IDS[4] / "state.json").write_text("{broken", "utf-8")
    (ws / "episodes" / IDS[4] / "state.json.bak").unlink(missing_ok=True)
    eps = client.get("/api/episodes").json()["episodes"]
    assert [e["id"] for e in eps] == IDS and "error" in eps[4] and "error" not in eps[0]


def test_learning_page_still_sees_every_episode(app, client):
    client.get("/api/learning")
    assert in_memory(app) == (set(), set())          # walked one at a time, nothing kept


def test_music_view_does_not_pin_closed_episodes(app, client):
    for eid in IDS[:4]:
        assert client.get(f"/api/episodes/{eid}/music").status_code == 200
    assert in_memory(app)[1] == set(IDS[1:4])
