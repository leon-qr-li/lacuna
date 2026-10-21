"""Episode / learning bugs found by the full scan of 2026-10-18: a deleted episode's learning evidence
stays (filed away under a name of its own, so the id is free again), and a request racing 永久删除 can't keep it alive."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from lacuna_app import create_app
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.store import Workspace

from .fake_lessons import FakeRuleWriter
from .synth import AI_EPISODE, make_ai_workspace, write_recordings


def client(root: Path, **svc) -> TestClient:
    svc.setdefault("rule_writer", FakeRuleWriter())
    return TestClient(create_app(root, MockEditorAdapter(), web_dist=Path("/nonexistent"), **svc))


def delete(c, episode_id):
    assert c.post(f"/api/episodes/{episode_id}/archive").status_code == 200
    assert c.delete(f"/api/episodes/{episode_id}").status_code == 200


def test_a_deleted_episodes_id_is_free_again(tmp_path):
    """Decision 2026-10-21-free-episode-ids: deleting files the evidence away, so the id is proposed
    and taken again (it used to be retired for good)."""
    ws = make_ai_workspace(tmp_path / "ws", "EP003")
    c = client(ws)
    assert c.get("/api/imports").json()["next_id"] == "EP004"
    delete(c, "EP003")
    assert c.get("/api/imports").json()["next_id"] == "EP001"        # nothing left: numbering starts over
    rec = write_recordings(tmp_path / "rec")
    r = c.post("/api/imports", json={"id": "EP003", "title": "新的一集", "tracks": [str(rec["Leon"]), str(rec["Pei"])]})
    assert r.status_code == 200, r.text


def test_the_deleted_episodes_verdicts_stay_in_its_snapshot(tmp_path):
    ws = make_ai_workspace(tmp_path / "ws")
    c = client(ws)
    ep = c.get(f"/api/episodes/{AI_EPISODE}").json()
    first = next(e for e in ep["edits"] if e["consequential"])
    c.post(f"/api/episodes/{AI_EPISODE}/edits/{first['id']}/review", json={"action": "restore"})
    delete(c, AI_EPISODE)
    c.get("/api/learning")
    assert not (ws / "learning" / "decisions" / f"{AI_EPISODE}.json").exists()
    [f] = (ws / "learning" / "decisions").glob(f"{AI_EPISODE}@*.json")
    snap = json.loads(f.read_text(encoding="utf-8"))
    assert snap["episode"] == f.name[:-5]
    assert any(d["edit_id"] == first["id"] and d["verdict"] == "restored" and d["episode"] == snap["episode"]
               for d in snap["decisions"])


def test_a_request_while_deleting_does_not_keep_the_episode_alive(tmp_path, monkeypatch):
    """Another tab polling the episode between "drop it from memory" and "move the folder away"
    cached it again, and the deleted episode kept answering (and taking edits) from memory."""
    import lacuna_app.archive as mod
    ws = make_ai_workspace(tmp_path / "ws")
    c = client(ws)
    c.post(f"/api/episodes/{AI_EPISODE}/archive")
    real = mod.gc.collect

    class G:
        @staticmethod
        def collect():
            assert c.get(f"/api/episodes/{AI_EPISODE}").status_code == 200    # the other tab
            return real()

    monkeypatch.setattr(mod, "gc", G)
    assert c.delete(f"/api/episodes/{AI_EPISODE}").status_code == 200
    assert not Workspace(ws).episode_dir(AI_EPISODE).exists()
    assert c.get(f"/api/episodes/{AI_EPISODE}").status_code == 404


def test_confirming_remember_again_for_a_rule_once_deleted_puts_it_back_in_force(tmp_path):
    """Leon deleted a rejected ask rule; later he 记住 the same words and confirms: it used to 404
    (and still write the ask), the rule staying deleted."""
    ws = make_ai_workspace(tmp_path / "ws")
    c = client(ws)
    ep = f"/api/episodes/{AI_EPISODE}"
    d = c.post(f"{ep}/remember", json={"text": "Pei 的嗯都别删", "playhead": 1.0}).json()["remember"]
    rid = c.post(f"{ep}/remember/{d['id']}", json={"action": "confirm"}).json()["rule"]
    assert c.post("/api/learning/rules", json={"id": rid, "action": "reject"}).status_code == 200
    assert c.post("/api/learning/rules", json={"id": rid, "action": "delete"}).status_code == 200
    d2 = c.post(f"{ep}/remember", json={"text": "Pei 的嗯都别删", "playhead": 2.0}).json()["remember"]
    r = c.post(f"{ep}/remember/{d2['id']}", json={"action": "confirm"})
    assert r.status_code == 200, r.text
    rules = {x["id"]: x for x in c.get("/api/learning").json()["rules"]}
    assert rules[r.json()["rule"]]["state"] == "approved"
