"""Audio hours (lacuna_app/quota.py, decision 2026-10-24-hour-metering): counted when an import succeeds,
against the account that made the show; refused when nothing is left; extra hours from the admin."""
from __future__ import annotations

import shutil

import pytest

from lacuna_app import quota
from lacuna_app.importer import Importer
from tests.app.synth import write_recordings
from tests.app.test_spaces import join, setup

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


def tracks(h: float, name: str = "a.wav") -> dict:
    return {"L": {"name": name, "size": 100, "duration": h * 3600}, "P": {"name": "b" + name, "size": 90, "duration": h * 3500}}


@pytest.fixture
def site(tmp_path):
    ws, leon = setup(tmp_path)
    beta = join(leon, "beta@example.com", plan="basic")
    meter = leon.app.state.meter
    sid = beta.get("/api/spaces").json()["current"]["id"]
    show = beta.get("/api/show").json()
    assert beta.put("/api/show", json=show | {"show_name": "测试", "hosts": [{"name": "Leon"}, {"name": "Pei"}]}).status_code == 200
    return ws, leon, beta, meter, sid


def test_import_counts_once_against_the_shows_maker(site):
    ws, leon, beta, meter, sid = site
    folder = meter.spaces.path(sid)
    assert meter.show_of(folder) == sid and meter.payer(folder) == (sid, "beta@example.com")
    meter.charge(folder, "EP001", {"tracks": tracks(1.5)})
    a = meter.account("beta@example.com")
    assert a["used"] == 1.5 and a["allowance"] == 4 and a["left"] == 2.5
    # the same files again this month (deleted and imported anew): free
    meter.charge(folder, "EP001", {"tracks": tracks(1.5)})
    assert meter.account("beta@example.com")["used"] == 1.5
    assert meter.month_total() == 3.0          # the server still did the work twice (capacity)
    p = beta.get("/api/plan").json()
    assert p["hours_used"] == 1.5 and p["hours"]["left"] == 2.5


def test_nothing_left_refuses_the_next_import_with_a_way_out(site, tmp_path):
    ws, leon, beta, meter, sid = site
    folder = meter.spaces.path(sid)
    meter.charge(folder, "EP001", {"tracks": tracks(3.9)})
    meter.allow(folder, tracks(1.0, "c.wav"))                 # 0.1 h left: may still start (may go over)
    meter.charge(folder, "EP002", {"tracks": tracks(1.0, "c.wav")})
    with pytest.raises(quota.QuotaError, match="4 小时音频额度已经用完"):
        meter.allow(folder, tracks(0.5, "d.wav"))
    # over HTTP, in the show's own app: the import is refused before anything runs
    rec = write_recordings(tmp_path / "rec")
    r = beta.post("/api/imports", json={"id": "EP003", "tracks": [str(rec["Leon"]), str(rec["Pei"])]})
    assert r.status_code == 422 and "额度已经用完" in r.json()["detail"] and "「想要更多时长」" in r.json()["detail"]
    # the owner approves 2 more hours this month: it starts again
    from lacuna_app.admin_store import AdminStore
    store = AdminStore(meter.auth.db, meter.auth.now)
    req = store.add_hour_request("beta@example.com", 2, "", False)
    store.decide_hours(req["id"], "approved", "leon@example.com", 2)
    a = meter.account("beta@example.com")
    assert a["bonus"]["granted"] == 2 and a["allowance"] == 6
    meter.allow(folder, tracks(0.5, "d.wav"))


def test_must_fit_and_switching_the_rules_off(site):
    ws, leon, beta, meter, sid = site
    folder = meter.spaces.path(sid)
    meter.charge(folder, "EP001", {"tracks": tracks(3.5)})
    meter.save_settings({"must_fit": True})
    with pytest.raises(quota.QuotaError, match="只剩 0.5 小时"):
        meter.allow(folder, tracks(1.0, "x.wav"))
    meter.save_settings({"enforce": False})
    meter.allow(folder, tracks(9.0, "y.wav"))
    assert meter.settings() == quota.DEFAULTS | {"must_fit": True, "enforce": False}


def test_staff_are_counted_never_refused_and_the_trial_is_once(site, tmp_path):
    ws, leon, beta, meter, sid = site
    main = meter.spaces.path("main")
    assert meter.payer(main)[1] == "leon@example.com"
    meter.charge(main, "EP009", {"tracks": tracks(20)})
    assert meter.account("leon@example.com")["left"] < 0
    meter.allow(main, tracks(1, "z.wav"))
    trial = join(leon, "t@example.com", plan="trial")
    tsid = trial.get("/api/spaces").json()["current"]["id"]
    tf = meter.spaces.path(tsid)
    meter.charge(tf, "EP001", {"tracks": tracks(1.2)})
    with pytest.raises(quota.QuotaError, match="免费体验的 1 小时已经用完"):
        meter.allow(tf, tracks(0.2, "q.wav"))
    assert meter.account("t@example.com", now=meter.now() + 40 * 86400)["left"] < 0      # never comes back


def test_adopted_feedback_adds_an_hour_this_month(site):
    ws, leon, beta, meter, sid = site
    fb = leon.app.state.feedback
    item = fb.add("beta@example.com", "idea", "导出加 FLAC")
    fb.reply(item["id"], None, None, True)
    assert meter.account("beta@example.com")["bonus"]["feedback"] == 1
    assert meter.account("beta@example.com")["allowance"] == 5


def test_an_import_that_finishes_is_charged_one_that_fails_is_not(site, tmp_path):
    from lacuna_app.first_cut import ClaudeFirstCut
    from tests.app.fake_claude import FakeFirstCutAnthropic
    from tests.app.synth import fake_asr
    from lacuna_app.store import Workspace
    ws, leon, beta, meter, sid = site
    folder = meter.spaces.path(sid)
    rec = write_recordings(tmp_path / "rec2")
    imp = Importer(Workspace(folder), first_cut_factory=lambda: ClaudeFirstCut(client=FakeFirstCutAnthropic()),
                   asr_backend=fake_asr)
    imp.on_done = lambda eid, job: meter.charge(folder, eid, job)

    def broken(tag, x, progress):
        raise RuntimeError("识别崩了")
    imp.asr_backend = broken
    imp.start("EP001", "", [str(rec["Leon"]), str(rec["Pei"])], wait=True)
    assert imp.status("EP001")["state"] == "error" and meter.account("beta@example.com")["used"] == 0
    imp.asr_backend = fake_asr
    imp.resume("EP001", wait=True)
    assert imp.status("EP001")["state"] == "done"
    assert meter.account("beta@example.com")["used"] == round(60 / 3600, 2)


def test_admin_shows_usage_and_changes_the_rules(site):
    ws, leon, beta, meter, sid = site
    meter.charge(meter.spaces.path(sid), "EP001", {"tracks": tracks(2)})
    from lacuna_app.admin_metrics import AdminData
    from lacuna_app.admin_store import AdminStore
    st = leon.app.state
    data = AdminData(st.auth, st.spaces, st.feedback, AdminStore(st.auth.db, st.auth.now), ws, st)
    rows = {r["email"]: r for r in data.users()}
    assert rows["beta@example.com"]["hours_used"] == 2 and rows["beta@example.com"]["hours"] == 4
