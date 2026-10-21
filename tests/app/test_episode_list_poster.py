"""The home page's episode tiles show the chosen cover (routes/episodes.py poster_url)."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from lacuna_app import create_app
from lacuna_app.editor import MockEditorAdapter
from tests.app.synth import EPISODE, make_workspace


def rows(c):
    return {r["id"]: r for r in c.get("/api/episodes").json()["episodes"]}


def test_tile_has_the_chosen_poster_or_none(tmp_path):
    ws = make_workspace(tmp_path / "ws")
    c = TestClient(create_app(ws, MockEditorAdapter(), web_dist=tmp_path / "none"))
    assert rows(c)[EPISODE]["poster"] is None
    f = ws / "episodes" / EPISODE / "poster.json"
    f.write_text(json.dumps({"schema": 1, "episode": EPISODE, "variants": [], "chosen": None, "cover": None}), encoding="utf-8")
    assert rows(c)[EPISODE]["poster"] is None              # versions drawn, none chosen
    f.write_text(json.dumps({"schema": 1, "episode": EPISODE, "variants": [], "chosen": "v2", "cover": None}), encoding="utf-8")
    url = rows(c)[EPISODE]["poster"]
    assert url.startswith("/api/episodes/") and "/poster/v2.png?v=" in url
    f.write_text("{broken", encoding="utf-8")
    assert rows(c)[EPISODE]["poster"] is None              # a broken file never breaks the list
