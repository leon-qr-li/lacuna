"""A load-test site: the owner plus N invited people, each with their own show holding one long episode.

    python scripts/loadtest/make_site.py <out-dir> [--users 60] [--minutes 60] [--sr 44100] [--shared 5]

Everything is synthetic and local (tests/app/synth.py stretched to `--minutes`, tone "speech", an AI first
cut built from scripted ops): no AI call, no ASR, no mail. The long episode is built once; each show gets a
copy of its JSON with the recordings hard-linked (read-only, like the real raw tracks). `--shared` shows
also get a second person (editor), for co-editing load. Writes <out-dir>/site.json: per person the session
cookie, show, episode and reviewable edit ids, read by lacuna.js (k6) and serve.py.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

PW = "load-test-password-1"
EPISODE = "EP001"


def stretch_synth(minutes: float, sr: int) -> None:
    """Make tests/app/synth.py's one-minute conversation `minutes` long at `sr` (module globals)."""
    from tests.app import synth
    base = list(synth.TURNS)
    reps = max(1, int(round(minutes)))
    synth.TURNS = [(tr, a + 60.0 * k, b + 60.0 * k) for k in range(reps) for tr, a, b in base]
    synth.DUR = 60.0 * reps
    synth.SR = sr


def ops_doc(minutes: int) -> dict:
    """The synthetic first cut's eight in-window ops repeated every minute (about 8 edits a minute, a busy
    real first cut has 5-6)."""
    from tests.app import synth
    toks = synth.tokens_doc()["tracks"]
    starts = {tag: [x["start"] for x in t] for tag, t in toks.items()}
    import bisect

    def tok(tag: str, t: float) -> str:
        i = bisect.bisect_right(starts[tag], t + 1e-9) - 1
        return toks[tag][max(i, 0)]["id"]

    ops, n = [], 0
    for k in range(minutes):
        o = 60.0 * k

        def op(**kw):
            nonlocal n
            n += 1
            ops.append({"id": f"op{n:05d}", **kw})
        op(op="tighten_pause", track="both", at=o + 4.2, target_s=0.4, category="pause", reason="两人之间的空白 1.5 秒，收到 0.4 秒", confidence=0.9)
        op(op="cut", track="P", **{"from": tok("P", o + 11.0), "to": tok("P", o + 11.0)}, category="crosstalk", reason="压在 Leon 说话下的附和", confidence=0.8)
        op(op="cut", track="L", **{"from": tok("L", o + 18.2), "to": tok("L", o + 20.0)}, category="repetition", reason="同一句话说了两遍，保留第二遍", confidence=0.7)
        op(op="slip", track="P", **{"from": tok("P", o + 22.3), "to": tok("P", o + 22.6)}, delta_s=0.5, category="interjection_move", reason="嗯 挪到 Leon 句末的停顿", confidence=0.4)
        op(op="cut", track="both", **{"from": tok("L", o + 26.5), "to": tok("L", o + 29.6)}, category="content", reason="这段题外话和主线无关", confidence=0.55)
        op(op="keep_flag", track="L", **{"from": tok("L", o + 36.5), "to": tok("L", o + 37.7)}, suggested="cut", category="content", reason="可能离题", confidence=0.5)
        op(op="tighten_pause", track="both", at=o + 44.2, target_s=0.6, category="pause", reason="空白 2.0 秒，收到 0.6 秒", confidence=0.85)
        op(op="cut", track="L", **{"from": tok("L", o + 48.1), "to": tok("L", o + 48.4)}, category="disfluency", reason="嗯 呃 口误", confidence=0.75)
    return {"episode": "LOAD", "model": "synthetic", "ops": ops}


def build_episode(dst: Path, minutes: int, sr: int) -> None:
    """One long episode in workspace `dst` (raw tracks under it)."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import make_ai_episode
    from lacuna_app.ai_cut import TrackTokens
    from lacuna_app.episode import create_episode
    from lacuna_app.store import Workspace
    from tests.app import synth
    stretch_synth(minutes, sr)
    t = time.time()
    refs = synth.write_raw(dst / "episodes" / EPISODE / "raw")
    print(f"  raw tracks {time.time() - t:.0f}s", flush=True)
    tokens = {tag: TrackTokens(x) for tag, x in synth.tokens_doc()["tracks"].items()}
    project, edits, transcript, _ = make_ai_episode.build(refs, ops_doc(minutes), tokens, 1.0, synth.DUR - 2.0)
    create_episode(Workspace(dst), EPISODE, {"title": f"压测 · {minutes} 分钟", "demo": False, "raw_offset_s": 1.0,
                                             "source": "ai_cut:synthetic"}, project, edits, transcript)
    print(f"  episode built {time.time() - t:.0f}s, {len(edits)} edits", flush=True)


def copy_episode(src_ws: Path, dst_ws: Path) -> None:
    """The episode's JSON copied, its recordings hard-linked (same paths stay valid: refs are absolute)."""
    src, dst = src_ws / "episodes" / EPISODE, dst_ws / "episodes" / EPISODE
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, copy_function=os.link)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("--users", type=int, default=60)
    ap.add_argument("--minutes", type=int, default=60)
    ap.add_argument("--sr", type=int, default=44100)
    ap.add_argument("--shared", type=int, default=5)
    a = ap.parse_args()

    from fastapi.testclient import TestClient

    from lacuna_app.auth import COOKIE
    from lacuna_app.editor import MockEditorAdapter
    from lacuna_app.routes.spaces import SPACE_COOKIE
    from lacuna_app.server import create_app
    from tests.app.e2e.auth import FakeMailer

    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    ws, master = out / "ws", out / "master"
    print(f"building a {a.minutes}-minute episode at {a.sr} Hz …", flush=True)
    build_episode(master, a.minutes, a.sr)
    ws.mkdir(exist_ok=True)
    copy_episode(master, ws)        # the owner's own show ("main")

    app = create_app(ws, MockEditorAdapter(), web_dist=out / "_no_ui", mailer=FakeMailer())
    owner = TestClient(app)
    assert owner.post("/api/auth/register", json={"email": "owner@example.com", "password": PW}).status_code == 200
    people = [{"email": "owner@example.com", "cookie": owner.cookies.get(COOKIE), "show": "main"}]
    spaces = app.state.spaces
    for i in range(a.users):
        email = f"user{i:03d}@example.com"
        link = owner.post("/api/auth/invites", json={"email": email, "plan": "pro"}).json()["link"]
        c = TestClient(app)
        r = c.post("/api/auth/register", json={"invite": link.rsplit("/", 1)[1], "password": PW})
        assert r.status_code == 200, r.text
        sid = c.get("/api/spaces").json()["current"]["id"]
        copy_episode(master, spaces.path(sid))
        people.append({"email": email, "cookie": c.cookies.get(COOKIE), "show": sid, "client": c})
    # co-editing: the first `shared` people's shows also get the next person as an editor
    for i in range(min(a.shared, a.users // 2)):
        host, guest = people[1 + 2 * i], people[2 + 2 * i]
        spaces.set_member(host["show"], guest["email"], "editor", by=host["email"])
        host["partner"] = guest["email"]
        guest["also"] = host["show"]
    site = []
    for p in people:
        c = p.pop("client", owner)
        if p["show"] != "main":
            c.post("/api/spaces/switch", json={"id": p["show"]})
        ep = c.get(f"/api/episodes/{EPISODE}").json()
        edits = [e["id"] for e in ep["edits"] if e.get("consequential")]
        site.append({**p, "episode": EPISODE, "edits": edits, "rev": ep.get("rev")})
    (out / "site.json").write_text(json.dumps({"workspace": str(ws), "cookie": COOKIE, "space_cookie": SPACE_COOKIE,
                                               "people": site}, ensure_ascii=False, indent=1))
    print(f"site ready: {len(site)} people, {len(site[0]['edits'])} reviewable edits each → {out / 'site.json'}")


if __name__ == "__main__":
    main()
