"""scripts/keep_only_episode.py: clear a workspace down to one episode the app's own way (Leon 2026-10-18)."""
import json
import shutil

import pytest

from lacuna_app.learning import Learning
from lacuna_app.library import Library
from lacuna_app.store import Workspace, atomic_write_json, read_json
from scripts.keep_only_episode import main, plan

from .synth import AI_EPISODE, EPISODE, make_ai_workspace, make_workspace, seed_learning, write_music

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


def test_keeps_one_episode_and_its_music_only(tmp_path, capsys):
    root = make_ai_workspace(tmp_path / "ws")
    make_workspace(root)
    seed_learning(root)
    ws = Workspace(root)
    meta = ws.episode_dir(AI_EPISODE) / "episode.json"
    atomic_write_json(meta, read_json(meta) | {"title": "生化危机"})
    lib = Library(ws)
    used = lib.add_file(write_music(tmp_path / "in" / "used.wav", 2.0))
    other = lib.add_file(write_music(tmp_path / "in" / "other.wav", 3.0))
    atomic_write_json(ws.episode_dir(AI_EPISODE) / "music.json",
                      {"placements": [{"asset_id": used["id"]}]})
    learning = Learning(ws)
    rid = learning.overview()["rules"][0]["id"]
    learning.decide(rid, "approve")

    p = plan(ws, "生化危机")
    assert p["keep"]["id"] == AI_EPISODE and [e["id"] for e in p["delete_episodes"]] == [EPISODE]
    assert [a["id"] for a in p["move_assets"]] == [used["id"]]
    assert [a["id"] for a in p["remove_assets"]] == [other["id"]]
    assert main(["--workspace", str(root), "--keep", "生化危机", "--port", "1"]) == 0   # dry run
    assert ws.episode_ids() == sorted([AI_EPISODE, EPISODE]) and len(lib.assets()) == 2

    assert main(["--workspace", str(root), "--keep", "生化危机", "--apply", "--port", "1"]) == 0
    assert ws.episode_ids() == [AI_EPISODE]
    [a] = lib.assets()
    assert a["id"] == used["id"] and a["shared"] is False and a["episodes"] == [AI_EPISODE]
    assert (lib.dir / "_removed" / "other.wav").is_file()                # moved, never erased
    after = {r["id"]: r["state"] for r in Learning(ws).overview()["rules"]}
    assert after[rid] == "approved"                                       # learned rules stay
    assert any((root / "_backup").rglob("library.json"))
    assert "deleted" in capsys.readouterr().out


def test_refuses_an_unclear_episode_or_a_running_app(tmp_path):
    root = make_ai_workspace(tmp_path / "ws")
    with pytest.raises(SystemExit):
        plan(Workspace(root), "没有这一集")
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); s.listen()
        port = s.getsockname()[1]
        assert main(["--workspace", str(root), "--keep", AI_EPISODE, "--apply", "--port", str(port)]) == 2
    assert Workspace(root).episode_ids() == [AI_EPISODE]
