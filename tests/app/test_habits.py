"""剪辑力度 and approved learned rules follow the editor across projects (lacuna_app/habits.py,
routes/habits.py, routes/spaces.py habits_moved; Leon 2026-10-20 18:24Z picked "global level + per-host adjust")."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from lacuna_app import create_app, first_cut, habits, show
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.store import atomic_write_json
from tests.app.e2e.auth import FakeMailer
from tests.app.synth import make_workspace
from tests.app.test_spaces import PW, join, setup


def test_level_is_per_person_and_shared_by_their_projects(tmp_path):
    ws, leon = setup(tmp_path)
    pei = join(leon, "pei@example.com", space="main", space_role="editor")
    assert leon.get("/api/habits").json()["cut_level"] == "normal"
    assert leon.put("/api/habits", json={"cut_level": "firm"}).json()["cut_level"] == "firm"
    assert leon.put("/api/habits", json={"cut_level": "brutal"}).status_code == 422
    # Pei works in the same project but keeps her own level
    assert pei.get("/api/habits").json()["cut_level"] == "normal"
    assert leon.get("/api/show").json()["my_level"] == "firm"
    assert pei.get("/api/show").json()["my_level"] == "normal"
    # stored in Leon's home, by a hash of his address, not in the project
    home = habits.home_for(ws, "leon@example.com")
    assert json.loads((home / habits.FILE).read_text())["cut_level"] == "firm"
    assert "leon" not in home.name
    # his own new project uses the same level
    leon.post("/api/spaces", json={"name": "Side"})
    assert leon.get("/api/show").json()["my_level"] == "firm"


def test_habits_need_a_sign_in(tmp_path):
    ws, leon = setup(tmp_path)
    anon = TestClient(leon.app)
    assert anon.get("/api/habits").status_code == 401


def test_without_accounts_the_level_lives_in_the_folder(tmp_path):
    ws = make_workspace(tmp_path / "ws")
    c = TestClient(create_app(ws, MockEditorAdapter(), web_dist=tmp_path / "none", mailer=FakeMailer()))
    c.put("/api/habits", json={"cut_level": "gentle"})
    assert (ws / habits.FILE).is_file()
    assert c.get("/api/show").json()["my_level"] == "gentle"


def test_host_adjust_moves_the_editors_level_one_step():
    assert habits.host_level("same", "normal") == "normal"
    assert habits.host_level("more", "normal") == "firm"
    assert habits.host_level("less", "normal") == "gentle"
    assert habits.host_level("more", "firm") == "firm"          # kept in range
    assert habits.host_level("less", "gentle") == "gentle"


def test_old_per_host_levels_become_adjustments():
    p = show.normalise({"show_name": "X", "hosts": [
        {"name": "A", "cut_level": "firm"}, {"name": "B", "cut_level": "gentle"}, {"name": "C"},
        {"name": "D", "cut_adjust": "less", "cut_level": "firm"}]}, strict=True)
    assert [h["cut_adjust"] for h in p["hosts"]] == ["more", "less", "same", "less"]
    assert all("cut_level" not in h for h in p["hosts"])
    # Leon's show: Leon firmer than his level, Pei the same
    assert [h["cut_adjust"] for h in show.LEGACY["hosts"]] == ["more", "same"]


def test_prompts_follow_the_editors_level(tmp_path):
    p = show.normalise({"show_name": "X", "hosts": [{"name": "Ana", "cut_adjust": "more"}, {"name": "Bo"}]}, strict=True)
    home = tmp_path / "me"
    token = habits.HOME.set(home)
    try:
        normal = show.style_lines(p)
        assert show.LEVEL_EN["firm"] in normal.splitlines()[0] and show.LEVEL_EN["normal"] in normal.splitlines()[1]
        assert show.legacy_level_note() == ""
        legacy_normal = first_cut.system_prompt("- keep laughs", show.LEGACY)
        habits.set_level(home, "gentle")
        lines = show.style_lines(p).splitlines()
        assert show.LEVEL_EN["normal"] in lines[0] and show.LEVEL_EN["gentle"] in lines[1]
        # Leon's tuned prompt stays word for word, with one line on top when his level isn't the default
        legacy_gentle = first_cut.system_prompt("- keep laughs", show.LEGACY)
        assert legacy_gentle != legacy_normal and show.legacy_level_note() in legacy_gentle
        same = lambda x: " ".join(x.split())  # noqa: E731
        assert same(legacy_gentle.replace(show.legacy_level_note(), "")) == same(legacy_normal)
    finally:
        habits.HOME.reset(token)


def _rules(path):
    return json.loads(path.read_text())["rules"]


def test_approved_rules_move_to_the_managers_once(tmp_path):
    ws = make_workspace(tmp_path / "ws")
    # rules Leon approved before rules followed the editor (and a startup job's direct approvals)
    (ws / "learning").mkdir(exist_ok=True)
    atomic_write_json(ws / "learning" / "rules.json",
                      {"schema": 1, "rules": {"r1": {"state": "approved"}, "ask:stutter-char-20261020": {"state": "approved"}},
                       "accepted_as_is": ["EP001"]})
    leon = TestClient(create_app(ws, MockEditorAdapter(), web_dist=tmp_path / "none", mailer=FakeMailer()))
    leon.post("/api/auth/register", json={"email": "leon@example.com", "password": PW})
    mine = habits.home_for(ws, "leon@example.com") / "learning" / "rules.json"
    assert set(_rules(mine)) == {"r1", "ask:stutter-char-20261020"}
    assert json.loads(mine.read_text())["accepted_as_is"] == ["EP001"]
    assert (ws / "learning" / "rules.json").is_file()                 # the project's file stays
    # an editor (not a manager) starts with their own, empty set
    pei = join(leon, "pei@example.com", space="main", space_role="editor")
    pei.get("/api/learning")
    assert not (habits.home_for(ws, "pei@example.com") / "learning" / "rules.json").exists()
    # once: a later change to the project's file is not copied again
    atomic_write_json(ws / "learning" / "rules.json", {"schema": 1, "rules": {"r9": {"state": "approved"}}})
    TestClient(create_app(ws, MockEditorAdapter(), web_dist=tmp_path / "none", mailer=FakeMailer())).get("/api/version")
    assert "r9" not in _rules(mine)


def test_migration_waits_for_startup_jobs(tmp_path):
    """Rules a startup job approves into the project's file (stutter_rule_once, registered after spaces)
    still reach the managers: the move happens at the first request, not at registration."""
    ws = make_workspace(tmp_path / "ws")
    leon = TestClient(create_app(ws, MockEditorAdapter(), web_dist=tmp_path / "none", mailer=FakeMailer()))
    leon.post("/api/auth/register", json={"email": "leon@example.com", "password": PW})
    (ws / "auth" / "habits_moved.json").unlink()
    # a new build starts: a startup job writes an approval into the project's file before any request
    app = create_app(ws, MockEditorAdapter(), web_dist=tmp_path / "none", mailer=FakeMailer())
    (ws / "learning").mkdir(exist_ok=True)
    atomic_write_json(ws / "learning" / "rules.json", {"schema": 1, "rules": {"ask:x": {"state": "approved"}}})
    c = TestClient(app)
    c.post("/api/auth/login", json={"email": "leon@example.com", "password": PW})
    c.get("/api/learning")
    assert "ask:x" in _rules(habits.home_for(ws, "leon@example.com") / "learning" / "rules.json")
