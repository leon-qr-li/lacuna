"""Batch 9 (second full scan) security fixes: restoring a deleted admin is the owner's; ending someone's sessions or
resetting their two-step sign-in ends their admin sign-ins too; huge-pixel pictures are refused before decoding;
reset codes are counted under the lock (parallel requests can't pass the limits) and for every email alike."""
from __future__ import annotations

import io
import threading
import time

import pytest
from fastapi.testclient import TestClient

from lacuna_app.auth import Auth, AuthError
from lacuna_app.feedback import real_image
from tests.app.e2e.auth import FakeMailer
from tests.app.test_admin import MEMBER, OWNER, PW, WRITE, join, setup, sign_in, step_up, turn_on_2fa
from tests.app.test_auth import Clock


def test_only_the_owner_brings_back_a_deleted_admin(tmp_path):
    app, main, _ = setup(tmp_path)
    join(app, main)
    join(app, main, "kim@example.com")
    auth = app.state.auth
    for e in (MEMBER, "kim@example.com"):
        turn_on_2fa(app, e)
        auth.update_user(OWNER, e, role="admin")
    owner = sign_in(app)
    step_up(app, owner)
    assert owner.delete("/api/admin/users/kim@example.com", headers=WRITE).status_code == 200
    sam = sign_in(app, MEMBER)
    step_up(app, sam, MEMBER)
    tid = next(i["id"] for i in sam.get("/api/admin/trash").json()["items"] if i["kind"] == "user")
    assert sam.post(f"/api/admin/trash/user/{tid}/restore", headers=WRITE).status_code == 403
    assert "kim@example.com" not in auth.users
    assert owner.post(f"/api/admin/trash/user/{tid}/restore", headers=WRITE).status_code == 200
    assert auth.users["kim@example.com"]["role"] == "admin"


def test_main_site_trash_refuses_an_admin_restoring_an_admin(tmp_path):
    app, main, _ = setup(tmp_path)
    sam = join(app, main)
    join(app, main, "kim@example.com")
    auth = app.state.auth
    auth.update_user(OWNER, MEMBER, role="admin")
    auth.update_user(OWNER, "kim@example.com", role="admin")
    auth.delete_user(OWNER, "kim@example.com")
    assert sam.post("/api/site/trash/user/kim@example.com/restore").status_code == 403
    assert main.post("/api/site/trash/user/kim@example.com/restore").status_code == 200


def test_ending_sessions_and_resetting_two_step_end_admin_sign_ins(tmp_path):
    app, main, _ = setup(tmp_path)
    join(app, main)
    turn_on_2fa(app, MEMBER)
    app.state.auth.update_user(OWNER, MEMBER, role="admin")
    owner = sign_in(app)
    step_up(app, owner)
    sam = sign_in(app, MEMBER)
    assert sam.get("/api/admin/overview").status_code == 200
    assert owner.post(f"/api/admin/users/{MEMBER}/sessions/end", headers=WRITE).status_code == 200
    assert sam.get("/api/admin/overview").status_code == 401
    assert owner.get("/api/admin/overview").status_code == 200
    sam = sign_in(app, MEMBER)
    assert owner.post(f"/api/admin/users/{MEMBER}", json={"reset_2fa": True}, headers=WRITE).status_code == 200
    assert sam.get("/api/admin/overview").status_code == 401
    assert owner.get("/api/admin/overview").status_code == 200


def _png(w: int, h: int) -> bytes:
    from PIL import Image
    b = io.BytesIO()
    Image.new("L", (w, h)).save(b, "PNG", optimize=True)
    return b.getvalue()


def test_pictures_with_too_many_pixels_are_refused_before_decoding():
    assert real_image(_png(64, 32), "PNG")
    big = _png(7000, 7000)        # 49 M pixels in a small file
    assert len(big) < 600_000
    assert not real_image(big, "PNG")


def test_parallel_code_requests_cannot_pass_the_limits(tmp_path):
    class Slow(FakeMailer):
        def send(self, *a, **k):
            time.sleep(0.2)
            super().send(*a, **k)

    mailer = Slow()
    a = Auth(tmp_path, mailer)
    a.register_first(OWNER, PW, None, True)
    out = []

    def go():
        try:
            a.send_code(OWNER, "reset")
            out.append("sent")
        except AuthError as e:
            out.append(e.status)

    ts = [threading.Thread(target=go) for _ in range(10)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert out.count("sent") == 1 and len(mailer.outbox) == 1


def test_code_limits_answer_the_same_for_unknown_emails(tmp_path):
    clock = Clock()
    a = Auth(tmp_path, FakeMailer(), clock=clock)
    a.register_first(OWNER, PW, None, True)
    for email in (OWNER, "nobody@example.com"):
        a.send_code(email, "reset")
        with pytest.raises(AuthError, match="刚发过"):
            a.send_code(email, "reset")
        for _ in range(4):
            clock.t += 61
            a.send_code(email, "reset")
        clock.t += 61
        with pytest.raises(AuthError, match="明天"):
            a.send_code(email, "reset")
