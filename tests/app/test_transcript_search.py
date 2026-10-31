"""逐字稿搜索 (transcript_search.py, Leon 2026-10-31): every place a text is said in the current version, in time
order, cut words tagged, ignoring case, width, spaces and punctuation; timeline seconds follow the cuts."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lacuna_app import create_app
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.transcript_search import norm

from .synth import EPISODE, make_workspace

EP = f"/api/episodes/{EPISODE}"


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(make_workspace(tmp_path / "ws"), MockEditorAdapter(), web_dist=Path("/nonexistent")))


def find(client, q, v=None):
    return client.get(f"{EP}/transcript/search", params={"q": q, **({"v": v} if v else {})}).json()


def test_norm_folds_case_width_spaces_and_punctuation():
    assert norm(" Oppen heimer，") == "oppenheimer"
    assert norm("ＮＯＬＡＮ") == "nolan"
    assert norm("《诺兰》") == "诺兰"
    assert norm("…  ") == ""


def test_finds_every_place_in_time_order_across_words(client):
    r = find(client, "电影")
    starts = [h["start"] for h in r["hits"]]
    assert len(starts) >= 6 and starts == sorted(starts) and not r["more"]
    assert all(h["end"] > h["start"] and h["speaker"] in ("Leon", "Pei") for h in r["hits"])
    assert r["hits"][0]["speaker"] == "Leon" and r["hits"][0]["gone"] is False
    # spaces and punctuation in the query are ignored, so is an empty one
    assert [h["start"] for h in find(client, "电 影！")["hits"]] == starts
    assert find(client, "  ，")["hits"] == [] and find(client, "没有这句")["hits"] == []


def test_cut_words_are_found_and_tagged(client):
    # e003 cut Leon's 「一部」 around 25 s: still found, marked gone
    gone = [h for h in find(client, "我们今天聊一部")["hits"] if h["gone"]]
    assert gone and all(h["speaker"] == "Leon" for h in gone)


def test_times_follow_a_new_cut(client):
    before = find(client, "我们")["hits"]
    s = client.post(f"{EP}/manual/cut", json={"start": 0.4, "end": 2.0}).json()
    after = find(client, "我们", s["version"])["hits"]
    assert after[0]["gone"] and not before[0]["gone"]             # the first one is now struck through
    assert after[-1]["start"] < before[-1]["start"] - 1.0          # the rest moved up with the cut
    assert client.get(f"{EP}/transcript/search", params={"q": "电影", "v": "nope"}).status_code == 404
