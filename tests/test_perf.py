"""lacuna_app/perf.py: slow requests, long lock holds and loop stalls, without names or ids."""
from __future__ import annotations

import threading
import time

from fastapi.testclient import TestClient

from lacuna_app import perf
from lacuna_app.server import create_app
from tests.app.synth import EPISODE, make_workspace


def test_routes_are_masked():
    assert perf.route("GET", "/api/episodes/EP_洛城_42/manual/wave") == "GET /api/episodes/{ep}/manual/wave"
    assert perf.route("GET", "/api/episodes/x/audio/abc123def.wav") == "GET /api/episodes/{ep}/audio/{v}.wav"
    assert perf.route("POST", "/api/spaces/s_9f8e7d/members") == "POST /api/spaces/{id}/members"
    assert perf.route("GET", "/api/library/3f2a9c1d") == "GET /api/library/{x}"
    assert perf.route("GET", "/api/health") == "GET /api/health"


def test_lock_wait_and_holder_are_noted():
    lock = perf.TimedRLock()
    perf.holds.clear()
    got = threading.Event()

    def hold():
        tok = perf.REQ.set({"route": "POST /api/episodes/{ep}/manual/cut", "lock_wait": 0.0, "holders": set()})
        with lock:
            with lock:               # re-entrant
                got.set()
                time.sleep(0.6)
        perf.REQ.reset(tok)

    t = threading.Thread(target=hold)
    t.start()
    got.wait()
    rec = {"route": "GET /api/episodes/{ep}/manual/wave", "lock_wait": 0.0, "holders": set()}
    tok = perf.REQ.set(rec)
    with lock:
        pass
    perf.REQ.reset(tok)
    t.join()
    assert rec["lock_wait"] > 0.3
    assert rec["holders"] == {"POST /api/episodes/{ep}/manual/cut"}
    assert perf.holds[-1]["by"] == "POST /api/episodes/{ep}/manual/cut" and perf.holds[-1]["s"] >= 0.5
    assert lock.holder is None


def test_slow_requests_are_reported(tmp_path, monkeypatch):
    ws = make_workspace(tmp_path / "ws")
    monkeypatch.setattr(perf, "SLOW_S", 0.0)       # every request counts as slow here
    perf.slow.clear()
    c = TestClient(create_app(ws))
    assert c.get(f"/api/episodes/{EPISODE}").status_code == 200
    out = c.get("/api/health/perf").json()
    hit = [s for s in out["slow"] if s["route"] == "GET /api/episodes/{ep}"]
    assert hit and hit[0]["status"] == 200 and "lock_wait" in hit[0]
    assert EPISODE not in str(out)
