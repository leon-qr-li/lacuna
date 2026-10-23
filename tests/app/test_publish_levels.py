"""How detailed the show-notes timeline is (Leon 2026-10-23, version A): 精简 / 标准 / 详细 on the publish
page. The writer ranks every entry once; a level only filters locally (no AI call)."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lacuna_app import Episode, Workspace, create_app
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.publish import DEFAULT_LEVEL, LEVELS, TOOL, ClaudePublisher, Publisher, clean, segments, thin

from .fake_claude import FakePublishAnthropic
from .synth import EPISODE, make_workspace

EP = f"/api/episodes/{EPISODE}"


@pytest.fixture
def ws(tmp_path):
    return Workspace(make_workspace(tmp_path / "ws"))


@pytest.fixture
def ep(ws):
    e = Episode(ws, EPISODE)
    yield e
    e.close()


@pytest.fixture
def fake():
    return FakePublishAnthropic()


@pytest.fixture
def pub(ws, fake):
    return Publisher(ws, lambda: ClaudePublisher(client=fake))


def row(t, rank, section=0, music=False):
    r = {"t": t, "rank": rank, "section": section, "text": f"{t}", "gone": False}
    return r | {"music": True} if music else r


def timeline(md: str) -> list[str]:
    part = md.split("## ⏱ 时间轴")[1].split("\n---")[0]
    return [ln for ln in part.splitlines() if ln.startswith("- **")]


# ---------------------------------------------------------------------------- the rule

def test_an_hour_long_timeline_gets_shorter_level_by_level():
    # an entry every minute for an hour, ranked 1 every 6th, 2 every 3rd, else 3; a part every 15 min
    rows = [row(60.0 * i, 1 if i % 6 == 0 else 2 if i % 3 == 0 else 3, section=i // 15) for i in range(60)]
    n = {k: len(thin(rows, k)) for k in LEVELS}
    assert n["full"] == 60                       # 详细 = what the writer wrote at today's density
    assert 15 <= n["std"] <= 25                  # 标准 ≈ every 3 min
    assert 8 <= n["lean"] <= 13                  # 精简 ≈ every 5 min
    for k in LEVELS:
        kept = [r["t"] for r in thin(rows, k)]
        firsts = {60.0 * 15 * s for s in range(4)}
        assert firsts <= set(kept)               # every part keeps its first line
        gaps = [b - a for a, b in zip(kept, kept[1:]) if b not in firsts]
        assert min(gaps) >= LEVELS[k]["gap"]


def test_a_one_minute_episode_no_longer_gets_a_line_every_few_seconds():
    rows = [row(4.0 * i, 2, section=i // 4) for i in range(12)]     # 12 lines in 48 s, 3 parts
    assert [r["t"] for r in thin(rows, "std")] == [0.0, 16.0, 32.0]  # one per part
    assert len(thin(rows, "full")) == 12                             # 详细 is the person's own pick


def test_music_cues_always_stay_and_unknown_level_is_the_default():
    rows = [row(0.0, 1), row(5.0, 3), row(6.0, 3, music=True)]
    assert [r["t"] for r in thin(rows, "lean")] == [0.0, 6.0]
    assert thin(rows, "nope") == thin(rows, DEFAULT_LEVEL)


def test_the_writer_ranks_every_entry_and_a_missing_rank_is_a_main_point(ep):
    entry = TOOL["input_schema"]["properties"]["sections"]["items"]["properties"]["entries"]["items"]
    assert entry["properties"]["rank"]["enum"] == [1, 2, 3] and "rank" in entry["required"]
    brief = (Path(__file__).resolve().parents[2] / "lacuna_app" / "prompts" / "show_notes_brief.txt").read_text("utf-8")
    assert "Give every entry a rank" in brief
    segs = segments(ep)
    draft, _ = clean({"sections": [{"heading": "h", "entries": [
        {"segment": segs[0].id, "text": "a", "rank": 1}, {"segment": segs[1].id, "text": "b"},
        {"segment": segs[2].id, "text": "c", "rank": 7}]}]}, segs)
    assert [e["rank"] for e in draft["sections"][0]["entries"]] == [1, 2, 2]


# ---------------------------------------------------------------------------- the pack

def test_new_pack_is_standard_and_switching_is_local(ep, pub, fake):
    pub.start(ep, wait=True)
    v = pub.view(ep)["pack"]
    assert v["level"] == "std" == DEFAULT_LEVEL
    assert v["counts"]["full"] > v["counts"]["std"] >= 2         # the synthetic episode is 45 s, 2 parts
    assert len(timeline(v["markdown"])) == v["counts"]["std"]
    assert v["duration"] > 30
    pub.set_level(ep, "full", rev=v["rev"])
    v2 = pub.view(ep)["pack"]
    assert v2["level"] == "full" and len(timeline(v2["markdown"])) == v2["counts"]["full"]
    assert len(fake.requests) == 1                               # no second AI call
    assert v2["chapters"] == v["chapters"]                       # parts don't change
    # a regenerate keeps the level the person picked
    pub.start(ep, wait=True)
    assert pub.view(ep)["pack"]["level"] == "full"


def test_switching_replaces_hand_edits_and_retime_keeps_the_level(ep, pub):
    pub.start(ep, wait=True)
    pub.edit(ep, markdown="# 我改的\n")
    pub.set_level(ep, "lean")
    v = pub.view(ep)["pack"]
    assert v["edited"] is False and v["markdown"].startswith("# 合成的一期")
    ep.apply_op({"op": "cut", "start": int(1.0 * ep.sr), "end": int(2.0 * ep.sr), "tracks": None}, "删掉")
    pub.retime(ep)
    v = pub.view(ep)["pack"]
    assert v["level"] == "lean" and len(timeline(v["markdown"])) == v["counts"]["lean"]


def test_a_pack_from_before_levels_shows_as_it_was(ep, pub):
    pub.start(ep, wait=True)
    p = ep.dir / "publish.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d.pop("level")
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    assert pub.view(ep)["pack"]["level"] == "full"


def test_level_api(ws, fake):
    pub = Publisher(ws, lambda: ClaudePublisher(client=fake))
    client = TestClient(create_app(ws.root, MockEditorAdapter(), web_dist=Path("/nonexistent"), publisher=pub))
    assert client.put(f"{EP}/publish/level", json={"level": "lean"}).status_code == 404     # nothing generated yet
    pub.start(Episode(ws, EPISODE), wait=True)
    v = client.get(f"{EP}/publish").json()["pack"]
    r = client.put(f"{EP}/publish/level", json={"level": "full", "rev": v["rev"]})
    assert r.status_code == 200 and r.json()["pack"]["level"] == "full"
    assert client.put(f"{EP}/publish/level", json={"level": "lean", "rev": v["rev"]}).status_code == 409   # stale page
    assert client.put(f"{EP}/publish/level", json={"level": "most"}).status_code == 422
