"""用户反馈 (lacuna_app/feedback.py, routes/feedback.py): writing feedback with its page and screenshot, 我的反馈 and
the red dot, the owner's reply mail, the one-question prompts' rules and a show's three questions."""
from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from lacuna_app import create_app
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.feedback import PROMPT_GAP_S
from tests.app.e2e.auth import FakeMailer
from tests.app.synth import make_workspace

PW = "correct horse battery"
PNG = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 64).decode()


class Clock:
    def __init__(self):
        self.t = 1_800_000_000.0

    def __call__(self):
        return self.t


def setup(tmp_path):
    ws = make_workspace(tmp_path / "ws")
    mailer = FakeMailer()
    leon = TestClient(create_app(ws, MockEditorAdapter(), web_dist=tmp_path / "none", mailer=mailer, mail_inline=True))
    leon.post("/api/auth/register", json={"email": "leon@example.com", "password": PW, "name": "Leon"})
    return leon, mailer


def join(leon, email, lang=None):
    link = leon.post("/api/auth/invites", json={"email": email, "plan": "basic", **({"lang": lang} if lang else {})}).json()["link"]
    c = TestClient(leon.app)
    assert c.post("/api/auth/register", json={"invite": link.rsplit("/", 1)[1], "password": PW, "name": "Sam"}).status_code == 200
    return c


def test_feedback_is_kept_with_its_page_and_screenshot_for_the_owner_only(tmp_path):
    leon, _ = setup(tmp_path)
    sam = join(leon, "sam@example.com")
    r = sam.post("/api/feedback", json={
        "kind": "bug", "text": "导出卡在 80%", "source": "error", "shot": PNG,
        "context": {"page": "#/ep/E1/export", "episode": "E1", "at": 1122.4, "error": "混音出错", "lang": "zh",
                    "actions": [f"step {i}" for i in range(30)], "secret": "dropped"}},
        headers={"user-agent": "Mozilla/5.0 (Macintosh; Mac OS X 10_15) Chrome/130.0 Safari/537.36"})
    assert r.status_code == 200, r.text
    fid = r.json()["id"]
    mine = r.json()["items"]
    assert [(m["kind"], m["status"], m["shot"], m["episode"]) for m in mine] == [("bug", "received", True, "E1")]
    # the screenshot: the person and the owner can see it, nobody else
    assert sam.get(f"/api/feedback/{fid}/shot").status_code == 200
    assert leon.get(f"/api/feedback/{fid}/shot").content.startswith(b"\x89PNG")
    alex = join(leon, "alex@example.com")
    assert alex.get(f"/api/feedback/{fid}/shot").status_code == 404
    assert alex.get("/api/feedback/mine").json()["items"] == []
    # the owner's list (until the admin exists) has the page, the show, the last 20 steps, the browser
    assert sam.get("/api/feedback/all").status_code == 403
    item = leon.get("/api/feedback/all").json()["items"][0]
    ctx = item["context"]
    assert ctx["page"] == "#/ep/E1/export" and ctx["at"] == 1122.4 and ctx["error"] == "混音出错"
    assert len(ctx["actions"]) == 20 and ctx["actions"][-1] == "step 29" and "secret" not in ctx
    assert ctx["browser"] == "Chrome · macOS"
    assert item["show"]["id"] and item["email"] == "sam@example.com" and item["name"] == "Sam"
    # never into the event log
    rows = leon.app.state.auth.db.query("SELECT props FROM events")
    assert not any("80%" in r["props"] for r in rows)


def test_what_a_person_can_send(tmp_path):
    leon, _ = setup(tmp_path)
    sam = join(leon, "sam@example.com")
    assert sam.post("/api/feedback", json={"kind": "bug", "text": "  "}).status_code == 422
    assert sam.post("/api/feedback", json={"kind": "spam", "text": "x"}).status_code == 422
    assert sam.post("/api/feedback", json={"kind": "bug", "text": "x", "shot": "data:text/html;base64,PGI+"}).status_code == 422
    r = sam.post("/api/feedback", json={"kind": "idea", "text": "直接发到 Buzzsprout", "importance": "need",
                                        "source": "publish", "platforms": ["Apple Podcasts", "Spotify"]})
    assert r.status_code == 200
    r = sam.post("/api/feedback", json={"kind": "praise", "text": "口癖去得很干净", "quote_ok": True})
    items = {i["kind"]: i for i in leon.get("/api/feedback/all").json()["items"]}
    assert items["idea"]["importance"] == "need" and items["idea"]["platforms"] == ["Apple Podcasts", "Spotify"]
    assert items["idea"]["source"] == "publish"
    assert items["praise"]["quote_ok"] is True
    assert TestClient(leon.app).post("/api/feedback", json={"kind": "bug", "text": "x"}).status_code == 401


def test_the_owner_replies_the_person_sees_a_red_dot_and_gets_a_mail_in_their_language(tmp_path):
    leon, mailer = setup(tmp_path)
    sam = join(leon, "sam@example.com", lang="en")
    fid = sam.post("/api/feedback", json={"kind": "idea", "text": "Publish to Buzzsprout"}).json()["id"]
    assert sam.get("/api/feedback/mine").json()["unread"] == 0
    sent = len(mailer.outbox)
    r = leon.post(f"/api/feedback/{fid}/reply", json={"text": "On our list for after beta.", "status": "planned",
                                                       "adopted": True})
    assert r.status_code == 200 and r.json()["mailed"] is True
    mail = mailer.outbox[sent:]
    assert [m["to"] for m in mail] == ["sam@example.com"]
    assert mail[0]["subject"] == "Your LACUNA feedback has a reply"
    assert "On our list for after beta." in mail[0]["text"] and "Planned" in mail[0]["text"]
    assert "1 extra editing hour" in mail[0]["text"] and "#/feedback" in mail[0]["text"]
    got = sam.get("/api/feedback/mine").json()
    assert got["unread"] == 1
    it = got["items"][0]
    assert it["status"] == "planned" and it["adopted"] is True and it["bonus_hours"] == 1
    assert [x["text"] for x in it["replies"]] == ["On our list for after beta."]
    assert sam.post("/api/feedback/mine/seen").json()["unread"] == 0
    assert sam.get("/api/feedback/mine").json()["unread"] == 0
    # only the owner / admins reply; bad status refused; unknown id
    assert sam.post(f"/api/feedback/{fid}/reply", json={"text": "x"}).status_code == 403
    assert leon.post(f"/api/feedback/{fid}/reply", json={"status": "maybe"}).status_code == 422
    assert leon.post("/api/feedback/fb_nope/reply", json={"text": "x"}).status_code == 404


def test_a_deleted_account_takes_its_feedback_with_it(tmp_path):
    leon, _ = setup(tmp_path)
    sam = join(leon, "sam@example.com")
    fid = sam.post("/api/feedback", json={"kind": "bug", "text": "x", "shot": PNG}).json()["id"]
    fb = leon.app.state.feedback
    assert fb.shot_path(fid)
    leon.app.state.auth.delete_user("leon@example.com", "sam@example.com")
    assert fb.get(fid) is None and fb.shot_path(fid) is None


def test_prompts_rate_after_the_first_export_pmf_after_the_third_at_most_once_a_week(tmp_path):
    leon, _ = setup(tmp_path)
    sam = join(leon, "sam@example.com")
    fb = leon.app.state.feedback
    clock = Clock()
    fb.now = clock
    log = leon.app.state.events
    uid = leon.app.state.auth.user_id("sam@example.com")
    sid = sam.get("/api/spaces").json()["current"]["id"]

    def export(ep):
        log.add("export.start", uid, sid, ep)

    assert sam.get("/api/feedback/prompt").json()["ask"] is None
    export("E1")
    export("E1")
    assert sam.get("/api/feedback/prompt").json() == {"ask": "rate", "exported": 1}
    # 以后再说: not again within the week
    assert sam.post("/api/feedback/prompt", json={"kind": "rate", "outcome": "later"}).status_code == 200
    assert sam.get("/api/feedback/prompt").json()["ask"] is None
    clock.t += PROMPT_GAP_S + 1
    assert sam.get("/api/feedback/prompt").json()["ask"] == "rate"
    bad = sam.post("/api/feedback/prompt", json={"kind": "rate", "outcome": "sent", "answer": {"stars": 9}})
    assert bad.status_code == 422
    r = sam.post("/api/feedback/prompt", json={"kind": "rate", "outcome": "sent",
                                               "answer": {"stars": 4, "saved": "1-2h", "text": "笑声剪短了"}})
    assert r.status_code == 200
    export("E2")
    export("E3")
    assert sam.get("/api/feedback/prompt").json()["ask"] is None          # a week since the last question
    clock.t += PROMPT_GAP_S + 1
    assert sam.get("/api/feedback/prompt").json()["ask"] == "pmf"
    sam.post("/api/feedback/prompt", json={"kind": "pmf", "outcome": "sent", "answer": {"choice": "very"}})
    clock.t += PROMPT_GAP_S + 1
    assert sam.get("/api/feedback/prompt").json()["ask"] is None          # both answered
    answers = {i["kind"]: i for i in leon.get("/api/feedback/all").json()["items"]}
    assert answers["rate"]["stars"] == 4 and answers["rate"]["saved"] == "1-2h" and answers["pmf"]["choice"] == "very"
    # prompt answers are not 我的反馈
    assert sam.get("/api/feedback/mine").json()["items"] == []


def test_never_ask_again_and_the_sample_show_does_not_count(tmp_path):
    leon, _ = setup(tmp_path)
    sam = join(leon, "sam@example.com")
    log = leon.app.state.events
    uid = leon.app.state.auth.user_id("sam@example.com")
    sample = sam.post("/api/onboarding/sample", json={"lang": "zh"}).json()["sample"]["id"]
    log.add("export.start", uid, sample, "SAMPLE_01")
    assert sam.get("/api/feedback/prompt").json()["ask"] is None              # in the sample show
    own = next(m["id"] for m in sam.get("/api/spaces").json()["mine"] if not m["sample"])
    assert leon.app.state.feedback.due("sam@example.com", 0) is None
    log.add("export.start", uid, own, "E1")
    fb = leon.app.state.feedback
    assert fb.due("sam@example.com", 1) == "rate"
    fb.prompt_result("sam@example.com", "rate", "never")
    fb.now = lambda: 9e12
    assert fb.due("sam@example.com", 5) is None
    # the owner can reset it (to test the prompts with a test account); nobody else
    assert sam.post("/api/feedback/prompt/reset", json={"email": "sam@example.com"}).status_code == 403
    assert leon.post("/api/feedback/prompt/reset", json={"email": "nobody@example.com"}).status_code == 404
    assert leon.post("/api/feedback/prompt/reset", json={"email": "Sam@example.com"}).json()["ok"] is True
    assert fb.due("sam@example.com", 5) == "pmf"


def test_a_new_show_keeps_its_three_answers_for_the_owner(tmp_path):
    leon, _ = setup(tmp_path)
    sam = join(leon, "sam@example.com")
    own = sam.get("/api/spaces").json()["mine"][0]["id"]
    r = sam.post("/api/feedback/profile", json={"show": own, "lang": "mixed", "region": "na", "editing": "self"})
    assert r.json() == {"lang": "mixed", "region": "na", "editing": "self"}
    # without a show: the one Sam is in, with that show's own language setting
    r = sam.post("/api/feedback/profile", json={"region": "na"})
    assert r.json()["region"] == "na" and r.json()["lang"] in ("zh", "en")
    # unknown answers are dropped; someone else's show is refused
    assert "region" not in sam.post("/api/feedback/profile", json={"show": own, "region": "mars"}).json()
    alex = join(leon, "alex@example.com")
    assert alex.post("/api/feedback/profile", json={"show": own, "region": "na"}).status_code == 404
    sam.post("/api/feedback/profile", json={"show": own, "region": "eu", "editing": "new"})
    sam.post("/api/feedback", json={"kind": "bug", "text": "x"})
    item = leon.get("/api/feedback/all").json()["items"][0]
    assert item["profile"]["region"] == "eu" and item["profile"]["editing"] == "new"


def test_the_server_script_answers_for_the_owner_until_the_admin_exists(tmp_path, capsys):
    """Leon's 验收 (decision 2026-10-24-user-feedback): Claude replies from the server's command line; the person
    sees it exactly as from the admin later."""
    from scripts.feedback_admin import main
    leon, _ = setup(tmp_path)
    sam = join(leon, "sam@example.com", lang="en")
    fid = sam.post("/api/feedback", json={"kind": "bug", "text": "Export stuck at 80%"}).json()["id"]
    ws = str(tmp_path / "ws")
    assert main(["--workspace", ws, "list", "--email", "sam@example.com"]) == 0
    assert fid in capsys.readouterr().out
    assert main(["--workspace", ws, "show", fid]) == 0
    assert "Export stuck at 80%" in capsys.readouterr().out
    mailer = FakeMailer()
    assert main(["--workspace", ws, "reply", fid, "--text", "Fixed, thanks!", "--status", "fixed"], mailer=mailer) == 0
    assert [m["to"] for m in mailer.outbox] == ["sam@example.com"]
    assert mailer.outbox[0]["subject"] == "Your LACUNA feedback has a reply" and "Fixed, thanks!" in mailer.outbox[0]["text"]
    got = sam.get("/api/feedback/mine").json()
    assert got["unread"] == 1 and got["items"][0]["status"] == "fixed"
    assert main(["--workspace", ws, "reply", "fb_nope", "--status", "fixed"], mailer=mailer) == 1
    assert main(["--workspace", ws, "reset-prompts", "nobody@example.com"]) == 1
    assert main(["--workspace", ws, "reset-prompts", "sam@example.com"]) == 0
