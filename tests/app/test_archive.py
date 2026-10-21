"""首检 #3: archive an episode, restore it, delete it for good - and the habits it taught stay.

Leon's rule (2026-10-17): deleting an episode removes its audio and episode files only; what
「学到的规则」 learned from it (learning/ evidence, rules) is never deleted.
"""
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lacuna_app import create_app
from lacuna_app.archive import Archive
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.store import Workspace

from .synth import AI_EPISODE, make_ai_workspace, make_workspace, write_recordings


def client(root: Path, **svc) -> TestClient:
    return TestClient(create_app(root, MockEditorAdapter(), web_dist=Path("/nonexistent"), **svc))


@pytest.fixture
def ws(tmp_path) -> Path:
    root = make_ai_workspace(tmp_path / "ws")
    make_workspace(root)                    # a second episode (the demo one) so the list isn't empty
    return root


def ids(c) -> list[str]:
    return [e["id"] for e in c.get("/api/episodes").json()["episodes"]]


def test_archive_hides_and_restore_brings_back(ws):
    c = client(ws)
    assert AI_EPISODE in ids(c) and c.get("/api/episodes").json()["archived"] == 0
    r = c.post(f"/api/episodes/{AI_EPISODE}/archive")
    assert r.status_code == 200 and r.json()["at"]
    assert AI_EPISODE not in ids(c)
    assert c.get("/api/episodes").json()["archived"] == 1
    arch = c.get("/api/archive").json()["episodes"]
    assert [e["id"] for e in arch] == [AI_EPISODE] and arch[0]["archived_at"] and arch[0]["title"]
    # archiving touches nothing inside the episode: it still opens
    assert c.get(f"/api/episodes/{AI_EPISODE}").status_code == 200
    assert c.post(f"/api/episodes/{AI_EPISODE}/restore").status_code == 200
    assert AI_EPISODE in ids(c) and c.get("/api/archive").json()["episodes"] == []
    assert c.post(f"/api/episodes/{AI_EPISODE}/restore").status_code == 409
    assert c.post("/api/episodes/nope/archive").status_code == 404
    assert c.post("/api/episodes/..%2F..%2Fx/archive").status_code in (400, 404)


def test_archive_survives_restart(ws):
    client(ws).post(f"/api/episodes/{AI_EPISODE}/archive")
    assert AI_EPISODE not in ids(client(ws))


def test_delete_needs_archive_first(ws):
    c = client(ws)
    r = c.delete(f"/api/episodes/{AI_EPISODE}")
    assert r.status_code == 409 and "归档" in r.json()["detail"]
    assert AI_EPISODE in ids(c)


def test_delete_for_good_keeps_learning_and_exports(ws, tmp_path):
    c = client(ws)
    ep = c.get(f"/api/episodes/{AI_EPISODE}").json()
    first = next(e for e in ep["edits"] if e["consequential"])
    assert c.post(f"/api/episodes/{AI_EPISODE}/edits/{first['id']}/review",
                  json={"action": "restore"}).status_code == 200          # a verdict 学到的规则 learns from
    edir = Workspace(ws).episode_dir(AI_EPISODE)
    (edir / "chat.json").write_text(json.dumps({"turns": [{"text": "以后 Pei 的嗯少删点"}]}, ensure_ascii=False),
                                    encoding="utf-8")
    exports = ws / "exports" / AI_EPISODE
    exports.mkdir(parents=True)
    (exports / "out.mp3").write_bytes(b"mp3")
    cache = ws / "imports" / AI_EPISODE
    cache.mkdir(parents=True)
    (cache / "asr_L.json").write_text("{}", encoding="utf-8")
    rules_before = (ws / "learning" / "rules.json").read_bytes() if (ws / "learning" / "rules.json").exists() else None
    assert not (ws / "learning" / "decisions" / f"{AI_EPISODE}.json").exists()   # never opened 学到的规则

    c.post(f"/api/episodes/{AI_EPISODE}/archive")
    r = c.delete(f"/api/episodes/{AI_EPISODE}")
    assert r.status_code == 200, r.text
    assert r.json()["freed_bytes"] > 0

    assert not edir.exists() and not cache.exists()
    assert AI_EPISODE not in ids(c) and c.get("/api/archive").json()["episodes"] == []
    assert c.get(f"/api/episodes/{AI_EPISODE}").status_code == 404
    assert not (ws / "episodes" / ".trash").exists()
    # what stays: the finished exports, and every bit of learning evidence
    assert (exports / "out.mp3").read_bytes() == b"mp3"
    filed = r.json()["learning_filed_as"]
    assert filed.startswith(f"{AI_EPISODE}@")
    snap = json.loads((ws / "learning" / "decisions" / f"{filed}.json").read_text(encoding="utf-8"))
    assert any(d["edit_id"] == first["id"] and d["verdict"] == "restored" for d in snap["decisions"])
    chat = json.loads((ws / "learning" / "chats" / f"{filed}.json").read_text(encoding="utf-8"))
    assert chat["turns"][0]["text"] == "以后 Pei 的嗯少删点"
    if rules_before is not None:
        assert (ws / "learning" / "rules.json").exists()
    # and 学到的规则 still counts the deleted episode's verdicts
    stats = c.get("/api/learning").json()["stats"]
    assert stats["decisions"] >= 1 and AI_EPISODE in json.dumps(stats, ensure_ascii=False)


def test_delete_never_touches_recordings_outside_the_workspace(tmp_path):
    """An imported episode reads Leon's own downloads in place; deleting it leaves them alone."""
    root = make_ai_workspace(tmp_path / "ws")
    rec = write_recordings(tmp_path / "Downloads")
    meta_p = Workspace(root).episode_dir(AI_EPISODE) / "episode.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    meta["raw_tracks"] = {k: str(v) for k, v in rec.items()}
    meta_p.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    c = client(root)
    c.post(f"/api/episodes/{AI_EPISODE}/archive")
    assert c.delete(f"/api/episodes/{AI_EPISODE}").status_code == 200
    assert all(p.is_file() for p in rec.values())


def test_delete_refused_while_importing(ws):
    class BusyImporter:
        def status(self, eid=None):
            return {"id": eid, "state": "running"} if eid else []

        def track_paths(self):
            return []

        def drop(self, eid):
            raise AssertionError("must not drop a running import")

    c = client(ws, importer=BusyImporter())
    c.post(f"/api/episodes/{AI_EPISODE}/archive")
    r = c.delete(f"/api/episodes/{AI_EPISODE}")
    assert r.status_code == 409 and "导入" in r.json()["detail"]
    assert Workspace(ws).episode_dir(AI_EPISODE).is_dir()


def test_locked_folder_leaves_everything_in_place(ws, monkeypatch):
    """Windows can refuse to move a folder whose files are open: then nothing is deleted."""
    import lacuna_app.archive as mod
    a = Archive(Workspace(ws))
    a.archive(AI_EPISODE)

    def refuse(src, dst):
        raise PermissionError("in use")

    monkeypatch.setattr(mod.os, "replace", refuse)
    with pytest.raises(mod.ArchiveError):
        a.delete(AI_EPISODE)
    assert AI_EPISODE in Workspace(ws).episode_ids() and a.is_archived(AI_EPISODE)


def test_new_import_with_a_deleted_id_starts_clean(ws):
    """The import cache goes with the episode, so a fresh import under the same id redoes ASR."""
    c = client(ws)
    cache = ws / "imports" / AI_EPISODE
    cache.mkdir(parents=True)
    (cache / "job.json").write_text(json.dumps({"id": AI_EPISODE, "state": "done", "tracks": {}, "created": "x"}),
                                    encoding="utf-8")
    c = client(ws)                                    # the importer lists that job at start
    assert any(j["id"] == AI_EPISODE for j in c.get("/api/imports").json()["jobs"])
    c.post(f"/api/episodes/{AI_EPISODE}/archive")
    assert c.delete(f"/api/episodes/{AI_EPISODE}").status_code == 200
    assert not cache.exists()
    assert not any(j["id"] == AI_EPISODE for j in c.get("/api/imports").json()["jobs"])
    shutil.rmtree(ws / "imports", ignore_errors=True)
