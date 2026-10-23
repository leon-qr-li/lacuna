"""入门 and LACUNA 示例节目 (routes/onboarding.py, sample.py): progress per person, the sample show that no
plan counts, reset and delete, the short version for collaborators."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from lacuna_app import create_app, sample
from lacuna_app.editor import MockEditorAdapter
from tests.app.e2e.auth import FakeMailer
from tests.app.synth import make_workspace

PW = "correct horse battery"


def setup(tmp_path):
    ws = make_workspace(tmp_path / "ws")
    leon = TestClient(create_app(ws, MockEditorAdapter(), web_dist=tmp_path / "none", mailer=FakeMailer(),
                                 mail_inline=True))
    leon.post("/api/auth/register", json={"email": "leon@example.com", "password": PW, "name": "Leon"})
    return leon


def join(leon, email, **extra):
    link = leon.post("/api/auth/invites", json={"email": email, "plan": "basic", **extra}).json()["link"]
    c = TestClient(leon.app)
    r = c.post("/api/auth/register", json={"invite": link.rsplit("/", 1)[1], "password": PW, "name": "Sam"})
    assert r.status_code == 200
    return c


def test_someone_with_episodes_starts_with_the_guide_hidden(tmp_path):
    leon = setup(tmp_path)
    got = leon.get("/api/onboarding").json()
    assert got["hidden"] is True and got["welcomed"] is True


def test_a_new_person_ticks_steps_and_it_is_kept_for_them(tmp_path):
    leon = setup(tmp_path)
    sam = join(leon, "sam@example.com")
    got = sam.get("/api/onboarding").json()
    assert got["hidden"] is False and got["welcomed"] is False and got["collab"] is None
    assert got["steps"] == ["show", "import", "review", "chat", "music", "export"]
    sam.post("/api/onboarding/mark", json={"step": "show"})
    sam.post("/api/onboarding/mark", json={"step": "show"})
    assert sam.post("/api/onboarding/mark", json={"step": "../x"}).status_code == 422
    assert sam.put("/api/onboarding", json={"welcomed": True}).json()["welcomed"] is True
    again = TestClient(leon.app)        # another browser
    again.post("/api/auth/login", json={"email": "sam@example.com", "password": PW})
    got = sam.get("/api/onboarding").json()
    assert got["done"] == ["show"] and got["welcomed"] is True
    assert leon.get("/api/onboarding").json()["done"] == []


def test_the_sample_show_is_free_resettable_and_removable(tmp_path):
    leon = setup(tmp_path)
    sam = join(leon, "sam@example.com")
    r = sam.post("/api/onboarding/sample", json={"lang": "en"})
    assert r.status_code == 200
    sid = r.json()["sample"]["id"]
    assert r.json()["sample"]["lang"] == "en"
    spaces = sam.get("/api/spaces").json()
    assert spaces["current"]["id"] == sid and spaces["current"]["sample"] is True
    # its episode is there, with the first cut done, and its show is set up
    eps = sam.get("/api/episodes").json()["episodes"]
    assert [e["id"] for e in eps] == ["SAMPLE_01"]
    assert sam.get("/api/show").json()["show_name"] == "LACUNA Sample Show"
    # it is not one of the plan's shows: 基础版 still lets Sam set up their own
    own = [m for m in spaces["mine"] if not m["sample"]]
    assert len(own) == 1
    # nobody can be invited into it
    assert sam.post(f"/api/spaces/{sid}/invite", json={"email": "alex@example.com"}).status_code == 403
    # adding it again gives the same show; reset brings the edits back and forgets the sample steps
    assert sam.post("/api/onboarding/sample", json={"lang": "zh"}).json()["sample"]["id"] == sid
    ep = sam.get("/api/episodes/SAMPLE_01").json()
    first = next(e for e in ep["edits"] if e["category"] == "content")
    assert sam.post(f"/api/episodes/SAMPLE_01/edits/{first['id']}/review", json={"action": "restore", "playhead": 0}).status_code == 200
    sam.post("/api/onboarding/mark", json={"step": "sample.decide"})
    sam.post("/api/onboarding/mark", json={"step": "show"})
    out = sam.post("/api/onboarding/sample/reset").json()
    assert out["done"] == ["show"]
    again = sam.get("/api/episodes/SAMPLE_01").json()
    assert next(e for e in again["edits"] if e["id"] == first["id"])["status"] == "applied"
    # the shared recording is outside the show's folder, and stays when the sample is deleted
    raw = tmp_path / "ws" / "sample" / f"v{sample.VERSION}" / "en" / "raw"
    assert sorted(p.name for p in raw.iterdir()) == ["Alex.wav", "Sam.wav"]
    assert sam.delete("/api/onboarding/sample").json()["sample"] is None
    assert all(not m["sample"] for m in sam.get("/api/spaces").json()["mine"])
    assert raw.is_dir()


def test_the_sample_matches_the_tour(tmp_path):
    """The bubble tour's numbers: 2:12 raw, five first-cut spots (three to review: a restart, a tangent, a
    corrected score; one 呃 and one pause routine), 2:12 → about 1:55, and three CC0 tracks in the library."""
    leon = setup(tmp_path)
    sam = join(leon, "sam@example.com")
    sam.post("/api/onboarding/sample", json={"lang": "zh"})
    ep = sam.get("/api/episodes/SAMPLE_01").json()
    assert 130 <= ep["raw_duration"] <= 133
    assert 112 <= ep["duration"] <= 117
    edits = ep["edits"]
    assert len(edits) == 5
    assert ep["pending_review"] == 3
    review = sorted((e for e in edits if e["consequential"]), key=lambda e: e["t"])
    assert [e["category"] for e in review] == ["filler", "content", "filler"]
    assert review[0]["t"] < 6 and 20 < review[1]["t"] < 32 and 36 < review[2]["t"] < 46
    assert sorted(e["category"] for e in edits if not e["consequential"]) == ["filler", "pause"]
    # the lines the tour points at are in the transcript
    lines = sam.get(f"/api/episodes/SAMPLE_01/manual/transcript?v={ep['version']}&t0=0&t1=200").json()
    said = "".join(w[0] for ln in (lines["lines"] if isinstance(lines, dict) else lines) for w in ln["words"])
    for line in ("那个演员叫什么来着", "等一下我喝口水"):
        assert line in said
    lib = sam.get("/api/library").json()["assets"]
    assert sorted(a["credit"]["title"] for a in lib) == ["Happy African Village", "Safari Time", "Uptown Fatness"]
    assert all(a["shared"] and a["credit"]["status"] == "confirmed" for a in lib)
    assert {a["kind"] for a in lib} == {"intro", "outro", "bed"}


def test_a_collaborator_gets_the_short_version(tmp_path):
    leon = setup(tmp_path)
    alex = join(leon, "alex@example.com", space="main", space_role="editor")
    got = alex.get("/api/onboarding").json()
    assert got["steps"] == ["review", "chat"]
    assert got["collab"]["by"] == "Leon"


def test_the_tour_line_in_the_sample_is_answered_without_the_ai(tmp_path):
    leon = setup(tmp_path)
    sam = join(leon, "sam@example.com")
    sam.post("/api/onboarding/sample", json={"lang": "zh"})
    before = sam.get("/api/episodes/SAMPLE_01").json()["duration"]
    out = sam.post("/api/episodes/SAMPLE_01/chat", json={"text": "把阿乔问演员名字的那两句删掉", "playhead": 40}).json()
    assert out["adapter"] == "sample" and "问演员名字的两句" in out["reply"]
    pid = out["proposal"]["id"]
    ep = sam.post(f"/api/episodes/SAMPLE_01/proposals/{pid}/approve", json={"playhead": 40}).json()
    assert 5 <= before - ep["duration"] <= 8      # about 1:55 → 1:49
    # said again once they are gone: the normal path (no scripted answer)
    again = sam.post("/api/episodes/SAMPLE_01/chat", json={"text": "把阿乔问演员名字的那两句删掉", "playhead": 40}).json()
    assert again.get("adapter") != "sample"


def test_the_tour_position_is_kept_and_reset(tmp_path):
    leon = setup(tmp_path)
    sam = join(leon, "sam@example.com")
    sam.post("/api/onboarding/sample", json={"lang": "zh"})
    assert sam.get("/api/onboarding").json()["tour"] is None
    assert sam.put("/api/onboarding", json={"tour": "music3"}).json()["tour"] == "music3"
    assert sam.put("/api/onboarding", json={"tour": "Bad Step!"}).status_code == 422
    assert sam.post("/api/onboarding/sample/reset").json()["tour"] is None
    # before / after: the first 30 s as recorded and the same stretch of the cut
    ab = sam.get("/api/episodes/SAMPLE_01/tour/raw").json()
    assert ab["before"]["duration"] == 30.0 and ab["after"]["duration"] == 30.0


def test_the_tour_music_line_is_answered_without_the_ai(tmp_path):
    leon = setup(tmp_path)
    sam = join(leon, "sam@example.com")
    sam.post("/api/onboarding/sample", json={"lang": "zh"})
    lib = sam.get("/api/library?episode=SAMPLE_01").json()
    assert len(lib["assets"]) == 3        # the three CC0 pieces are in the sample's library
    line = sample.TOUR_MUSIC["zh"]
    early = sam.post("/api/episodes/SAMPLE_01/music/chat", json={"text": line}).json()
    assert "先从左边的素材库放一段片头" in early["message"] and not early.get("draft")
    intro = next(a for a in lib["assets"] if a["kind"] == "intro")
    sam.post("/api/episodes/SAMPLE_01/music", json={"asset_id": intro["id"], "role": "intro"})
    out = sam.post("/api/episodes/SAMPLE_01/music/chat", json={"text": line}).json()
    assert "再压低 4 dB" in out["message"] and out["draft"]
    sam.post(f"/api/episodes/SAMPLE_01/music/draft/{out['draft']['id']}/accept")
    p = sam.get("/api/episodes/SAMPLE_01/music").json()["placements"][0]
    assert p["bg_db"] == 26


def test_the_tour_finds_its_spots_on_the_cut(tmp_path):
    leon = setup(tmp_path)
    sam = join(leon, "sam@example.com")
    sam.post("/api/onboarding/sample", json={"lang": "zh"})
    m = sam.get("/api/episodes/SAMPLE_01/tour/marks").json()
    assert m["hosts"] == ["小林", "阿乔"]
    for k in ("actor", "water", "cough"):
        a, b = m[k]
        assert 0 < a < b < 120, k
    assert m["actor"][1] < m["water"][0] < m["cough"][0]
    assert 0.3 < m["cough"][1] - m["cough"][0] < 0.6
    assert leon.get("/api/episodes/EP_TEST/tour/marks").status_code in (404, 403)


def test_the_tour_sentences_match_the_interface():
    """The tour fills these in through t(): the scripted answers must recognise both languages."""
    web = (Path(__file__).resolve().parents[2] / "web" / "src" / "features" / "tour" / "en.ts").read_text("utf-8")
    for d in (sample.TOUR_CHAT, sample.TOUR_MUSIC):
        assert f'"{d["zh"]}": "{d["en"]}"' in web
