"""Deleting an episode frees its id (decision 2026-10-21-free-episode-ids): the learning evidence is
filed away as ``<id>@<date>-<rand>``, keeps counting for 学到的规则, and a new episode under the old id
starts clean. Ids retired before this change are freed the same way (migration)."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from lacuna_app import create_app
from lacuna_app.archive import FILED_AWAY, episode_label, file_away, free_deleted_ids
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.store import Workspace

from .fake_lessons import FakeRuleWriter
from .synth import AI_EPISODE, make_ai_workspace


def client(root: Path) -> TestClient:
    return TestClient(create_app(root, MockEditorAdapter(), web_dist=Path("/nonexistent"),
                                 rule_writer=FakeRuleWriter()))


def put(root: Path, kind: str, name: str, doc) -> Path:
    p = root / "learning" / kind / f"{name}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return p


def decision(episode: str, edit_id: str = "e001") -> dict:
    return {"episode": episode, "edit_id": edit_id, "source": "first_cut", "kind": "disfluency",
            "category": "filler", "host": "Pei", "verdict": "restored", "how": "single", "confidence": 0.9,
            "length_s": 0.4, "speech_s": 0.4, "text": "嗯", "reason": "", "raw": [1.0, 1.4]}


def test_file_away_renames_every_kind_and_relabels_inside(tmp_path):
    ws = Workspace(tmp_path)
    put(tmp_path, "decisions", "EP001", {"episode": "EP001", "decisions": [decision("EP001"),
                                                                           decision("EP001.hand_edit", "h1")]})
    put(tmp_path, "asks", "EP001", {"episode": "EP001", "asks": [{"id": "a1", "title": "x"}]})
    put(tmp_path, "lessons", "EP001", {"episode": "EP001", "drafts": []})
    (tmp_path / "learning" / "chats").mkdir(parents=True)
    (tmp_path / "learning" / "chats" / "EP001.json").write_text("not json", encoding="utf-8")
    bak = put(tmp_path, "asks", "EP001", {"episode": "EP001", "asks": []}).with_name("EP001.json.bak")
    bak.write_text("{}", encoding="utf-8")

    new = file_away(ws, "EP001")
    assert new and new.startswith("EP001@") and FILED_AWAY.search(new)
    for kind in ("decisions", "asks", "lessons", "chats"):
        d = tmp_path / "learning" / kind
        assert not (d / "EP001.json").exists() and (d / f"{new}.json").exists(), kind
        assert not list(d.glob("*.bak")), kind
    doc = json.loads((tmp_path / "learning" / "decisions" / f"{new}.json").read_text(encoding="utf-8"))
    assert doc["episode"] == new
    assert [d["episode"] for d in doc["decisions"]] == [new, f"{new}.hand_edit"]
    # an unreadable file is moved as it is, never lost
    assert (tmp_path / "learning" / "chats" / f"{new}.json").read_text(encoding="utf-8") == "not json"
    assert file_away(ws, "EP001") is None               # nothing left under the old name


def test_migration_frees_old_retired_ids_only(tmp_path):
    root = make_ai_workspace(tmp_path / "ws")
    put(root, "decisions", "OLD-1", {"episode": "OLD-1", "decisions": [decision("OLD-1")]})
    put(root, "asks", "direct", {"episode": "direct", "asks": []})            # stutter rules: not an episode
    put(root, "asks", AI_EPISODE, {"episode": AI_EPISODE, "asks": []})        # a live episode's own
    put(root, "asks", "OLD-2@2026-10-01-ab12", {"episode": "OLD-2@2026-10-01-ab12", "asks": []})  # done already

    c = client(root)                                  # the app files them away at start
    names = {p.name for p in (root / "learning" / "decisions").glob("*.json")}
    assert "OLD-1.json" not in names and any(n.startswith("OLD-1@") for n in names)
    asks = {p.name for p in (root / "learning" / "asks").glob("*.json")}
    assert {"direct.json", f"{AI_EPISODE}.json", "OLD-2@2026-10-01-ab12.json"} <= asks
    assert free_deleted_ids(Workspace(root)) == {}    # a no-op the second time
    # the filed-away verdict still counts, and reads as a deleted episode
    stats = c.get("/api/learning").json()["stats"]
    assert any(e.startswith("OLD-1@") for e in stats["episodes"])


def test_new_episode_with_a_deleted_id_starts_with_no_old_lessons(tmp_path):
    root = make_ai_workspace(tmp_path / "ws")
    c = client(root)
    ep = f"/api/episodes/{AI_EPISODE}"
    d = c.post(f"{ep}/remember", json={"text": "Pei 的嗯都别删", "playhead": 1.0}).json()["remember"]
    rid = c.post(f"{ep}/remember/{d['id']}", json={"action": "confirm"}).json()["rule"]
    assert c.post(f"{ep}/archive").status_code == 200
    r = c.delete(ep)
    assert r.status_code == 200
    filed = r.json()["learning_filed_as"]
    assert not (root / "learning" / "asks" / f"{AI_EPISODE}.json").exists()
    assert (root / "learning" / "asks" / f"{filed}.json").exists()
    # the rule it taught is still there, its source shown as deleted
    rule = next(x for x in c.get("/api/learning").json()["rules"] if x["id"] == rid)
    assert "（已删）" in rule["detail"] and "@" not in rule["detail"]


def test_episode_label():
    assert episode_label("EP003@2026-10-21-a1b2") == "EP003（已删）"
    assert episode_label("EP003") == "EP003"
