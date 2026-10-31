"""用户动态 (decision 2026-10-31-admin-user-activity): the admin reads one account's events as a time window with
show and episode names, failed changes and details are logged without extra rows, and looking is audited."""
from __future__ import annotations

from fastapi.testclient import TestClient

from lacuna_app import create_app
from lacuna_app.editor import MockEditorAdapter
from tests.app.e2e.auth import FakeMailer
from tests.app.synth import AI_EPISODE, make_ai_workspace
from tests.app.test_admin import OWNER, PW, sign_in, turn_on_2fa

EP = f"/api/episodes/{AI_EPISODE}"


def setup(tmp_path):
    ws = make_ai_workspace(tmp_path / "ws")
    app = create_app(ws, MockEditorAdapter(), web_dist=tmp_path / "none", mailer=FakeMailer(), mail_inline=True,
                     no_admin_loop=True)
    main = TestClient(app)
    assert main.post("/api/auth/register", json={"email": OWNER, "password": PW, "name": "Leon"}).status_code == 200
    turn_on_2fa(app, OWNER)
    return app, main


def rows(app, ev=None):
    return [r for r in app.state.events.rows() if ev is None or r["ev"] == ev]


def test_a_failed_change_is_logged_with_its_status_and_refusals_are_not(tmp_path):
    app, main = setup(tmp_path)
    assert main.post(f"{EP}/manual/cut", json={"start": 5, "end": 2}).status_code == 422
    assert main.post("/api/episodes/NOPE/undo", json={}).status_code == 404
    failed = rows(app, "edit.manual.failed")
    assert [(r["ep"], r["props"]) for r in failed] == [(AI_EPISODE, {"status": 422})]
    assert not rows(app, "edit.undo.failed") and not rows(app, "edit.undo")


def test_details_go_in_the_request_s_own_row(tmp_path):
    app, main = setup(tmp_path)
    before = len(rows(app))
    r = main.post(f"{EP}/manual/cut", json={"start": 1.0, "end": 3.5})
    assert r.status_code == 200, r.text
    new = rows(app)[before:]
    assert [(x["ev"], x["props"]) for x in new] == [("edit.manual", {"seconds": 2.5})]


def test_the_admin_sees_a_window_of_activity_with_names_and_looking_is_audited_once(tmp_path):
    app, main = setup(tmp_path)
    assert main.post(f"{EP}/manual/cut", json={"start": 1.0, "end": 2.0}).status_code == 200
    log = app.state.events
    uid = log.uid(OWNER)
    log.add("export.start", uid, "main", AI_EPISODE)
    old = log.now() - 20 * 86400
    with log.db.tx() as c:
        c.execute("INSERT INTO events (ts, uid, sid, ep, ev, props) VALUES (?,?,?,?,?,?)",
                  (old, uid, "main", AI_EPISODE, "import.done", '{"audio_s": 3600}'))
    adm = sign_in(app)
    d = adm.get(f"/api/admin/users/{OWNER}/activity").json()
    assert d["user"]["email"] == OWNER and d["older"] is True
    evs = [r["ev"] for r in d["rows"]]
    assert evs[0] == "export.start" and "edit.manual" in evs and "import.done" not in evs
    top = d["rows"][0]
    assert top["show"] and top["ep"] == AI_EPISODE and top["title"]          # the episode's own title
    back = adm.get(f"/api/admin/users/{OWNER}/activity", params={"before": d["start"], "days": 31}).json()
    assert [r["ev"] for r in back["rows"]] == ["import.done"] and back["rows"][0]["props"] == {"audio_s": 3600}
    assert back["older"] is False
    adm.get(f"/api/admin/users/{OWNER}")                                     # the drawer: same look, no 2nd line
    lines = [a for a in adm.get("/api/admin/audit").json()["rows"] if a["action"] == "user.activity"]
    assert [a["target"] for a in lines] == [OWNER]
    assert adm.get("/api/admin/users/nobody@example.com/activity").status_code == 404


def test_an_export_s_end_is_logged_for_whoever_started_it(tmp_path):
    import time

    from lacuna_app import db as sitedb
    from lacuna_app.episode import Episode
    from lacuna_app.events import ACTOR, Actor, EventLog
    from lacuna_app.exporter import Exporter
    from lacuna_app.store import Workspace
    from tests.app.synth import EPISODE, make_workspace

    root = make_workspace(tmp_path / "ws")
    log = EventLog(sitedb.at(tmp_path / "site"), lambda e: None)
    ex = Exporter(Workspace(root))
    token = ACTOR.set(Actor(log, "u_1", "main"))
    try:
        ex.start(Episode(Workspace(root), EPISODE), ["wav"])            # runs in its own thread
    finally:
        ACTOR.reset(token)
    for _ in range(600):
        if ex.status(EPISODE)["state"] != "running":
            break
        time.sleep(0.05)
    done = [r for r in log.rows() if r["ev"] == "export.done"]
    assert [(r["uid"], r["ep"]) for r in done] == [("u_1", EPISODE)]
    assert done[0]["props"]["length_s"] > 0 and done[0]["props"]["formats"] == 1
