"""One-time cloud clean-out (Leon 2026-10-19): every episode, the library, exports and import caches go;
habits and learned rules (learning/), accounts, other workspaces and show settings stay. Runs once."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import lacuna_app.routes.clear_once as route
from lacuna_app import clear_once, create_app
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.store import Workspace

from .synth import AI_EPISODE, EPISODE, make_ai_workspace, make_workspace


def client(root: Path) -> TestClient:
    return TestClient(create_app(root, MockEditorAdapter(), web_dist=Path("/nonexistent")))


@pytest.fixture
def ws(tmp_path) -> Path:
    root = make_ai_workspace(tmp_path / "ws")
    make_workspace(root)
    # a verdict 「学到的规则」 learns from
    c = client(root)
    first = next(e for e in c.get(f"/api/episodes/{AI_EPISODE}").json()["edits"] if e["consequential"])
    assert c.post(f"/api/episodes/{AI_EPISODE}/edits/{first['id']}/review",
                  json={"action": "restore"}).status_code == 200
    for rel, body in {
        "library/library.json": '{"schema": 1, "assets": [], "series": []}',
        "library/music/theme.mp3": "mp3",
        f"exports/{AI_EPISODE}/out.mp3": "mp3",
        f"imports/{AI_EPISODE}/asr_L.json": "{}",
        "imported_tracks/abc/Leon.wav": "wav",
        "learning/lessons/EP_AI_合成.json": '{"lessons": []}',
        "learning/state.json": '{"rules": {}}',
        "auth/users.json": '{"users": []}',
        "spaces/s1/episodes/EP001/episode.json": "{}",
        "show.json": "{}",
        "names.json": "{}",
    }.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return root


@pytest.fixture
def cloud_on(monkeypatch):
    monkeypatch.setattr(route, "cloud", SimpleNamespace(enabled=lambda: True))


def test_clears_everything_but_learning_once(ws, cloud_on):
    c = client(ws)
    assert Workspace(ws).episode_ids() == []
    assert c.get("/api/episodes").json()["episodes"] == []
    for gone in ("library", "exports", "imports", "imported_tracks"):
        assert not (ws / gone).exists(), gone
    assert not (ws / "episodes" / ".trash").exists()
    # kept: habits and what they were learned from, accounts, other workspaces, show settings
    for kept in ("learning/lessons/EP_AI_合成.json", "learning/state.json", "auth/users.json",
                 "spaces/s1/episodes/EP001/episode.json", "show.json", "names.json"):
        assert (ws / kept).is_file(), kept
    snap = json.loads((ws / "learning" / "decisions" / f"{AI_EPISODE}.json").read_text(encoding="utf-8"))
    assert any(d["verdict"] == "restored" for d in snap["decisions"])
    stats = c.get("/api/learning").json()["stats"]
    assert stats["decisions"] >= 1
    assert clear_once.done(Workspace(ws))

    # runs once: an episode made afterwards survives the next start
    make_workspace(ws)
    client(ws)
    assert Workspace(ws).episode_ids() == [EPISODE]


def test_desktop_app_never_clears(ws, monkeypatch):
    monkeypatch.setattr(route, "cloud", SimpleNamespace(enabled=lambda: False))
    client(ws)
    assert sorted(Workspace(ws).episode_ids()) == sorted([AI_EPISODE, EPISODE])
    assert (ws / "library" / "music" / "theme.mp3").is_file()
    assert not clear_once.done(Workspace(ws))


def test_learning_not_saved_keeps_everything(ws, cloud_on, monkeypatch):
    """If an episode's learning cannot be snapshotted, it stays (not archived), and so do the
    library and exports; the next start tries again."""
    from lacuna_app import learning

    def broken(self, episodes=()):
        if any(e.id == AI_EPISODE for e in episodes):
            raise OSError("disk")
        return {}
    monkeypatch.setattr(learning.Learning, "overview", broken)
    c = client(ws)
    assert Workspace(ws).episode_ids() == [AI_EPISODE]
    assert [e["id"] for e in c.get("/api/episodes").json()["episodes"]] == [AI_EPISODE]
    assert (ws / "library" / "music" / "theme.mp3").is_file()
    assert (ws / "exports" / AI_EPISODE / "out.mp3").is_file()
    assert not clear_once.done(Workspace(ws))


def test_episode_with_missing_recordings_still_clears(ws, cloud_on):
    """Production's case: the raw tracks never reached the server; its learning is still kept."""
    import shutil
    shutil.rmtree(Workspace(ws).episode_dir(AI_EPISODE) / "raw")
    client(ws)
    assert Workspace(ws).episode_ids() == []
    assert (ws / "learning" / "decisions" / f"{AI_EPISODE}.json").is_file()
    assert clear_once.done(Workspace(ws))
