"""Project picture / colour, archive (已归档, read-only) and deleting a project for good
(lacuna_app/spaces.py, routes/spaces.py; decision projects-archive-delete)."""
from __future__ import annotations

import io

from PIL import Image

from lacuna_app import habits
from lacuna_app.spaces import COLORS, Spaces
from tests.app.test_spaces import EPISODE, join, setup


def png(w=300, h=200) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (w, h), (200, 30, 30)).save(b, "PNG")
    return b.getvalue()


def make(c, name):
    return c.post("/api/spaces", json={"name": name}).json()["created"]


def row(c, sid):
    return next(m for m in c.get("/api/spaces").json()["mine"] if m["id"] == sid)


def test_new_projects_get_different_colours(tmp_path):
    ws, leon = setup(tmp_path)
    made = [make(leon, f"P{i}") for i in range(4)]
    colours = [row(leon, s)["color"] for s in ["main", *made]]
    assert len(set(colours)) == 5 and set(colours) <= set(COLORS)
    assert row(leon, made[0])["picture"] is None


def test_old_projects_get_a_colour_once(tmp_path):
    (tmp_path / "auth").mkdir()
    (tmp_path / "auth" / "spaces.json").write_text(
        '{"spaces": [{"id": "main", "name": "A", "created": 1, "members": {}},'
        ' {"id": "sp_b", "name": "B", "created": 2, "members": {}}]}', encoding="utf-8")
    sp = Spaces(tmp_path)
    assert sp.spaces["main"]["color"] != sp.spaces["sp_b"]["color"]
    assert Spaces(tmp_path).spaces["sp_b"]["color"] == sp.spaces["sp_b"]["color"]


def test_picture_is_cut_square_and_only_managers_set_it(tmp_path):
    ws, leon = setup(tmp_path)
    r = leon.post("/api/spaces/main/picture", content=png(), headers={"content-type": "image/png"})
    assert r.status_code == 200
    url = row(leon, "main")["picture"]
    assert url.startswith("/api/spaces/main/picture?v=")
    got = leon.get(url)
    assert got.status_code == 200 and got.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(got.content)).size == (256, 256)
    assert leon.post("/api/spaces/main/picture", content=b"not an image").status_code == 400
    pei = join(leon, "pei@example.com", space="main", space_role="editor")
    assert pei.get(url).status_code == 200                       # members see it
    assert pei.post("/api/spaces/main/picture", content=png()).status_code == 403
    outsider = join(leon, "beta@example.com")
    assert outsider.get(url).status_code == 404
    assert leon.delete("/api/spaces/main/picture").status_code == 200
    assert row(leon, "main")["picture"] is None


def test_archived_project_is_read_only_for_everyone_until_restored(tmp_path):
    ws, leon = setup(tmp_path)
    pei = join(leon, "pei@example.com", space="main", space_role="editor")
    assert pei.post("/api/spaces/main/archive", json={"archived": True}).status_code == 403   # not a manager
    assert leon.post("/api/spaces/main/archive", json={"archived": True}).status_code == 200
    assert row(pei, "main")["archived"] is True
    for c in (leon, pei):
        assert c.get(f"/api/episodes/{EPISODE}").status_code == 200
        r = c.post(f"/api/episodes/{EPISODE}/undo")
        assert r.status_code == 403 and "已归档" in r.json()["detail"]
    assert leon.post("/api/spaces/main", json={"name": "新名字"}).status_code == 403
    assert leon.post("/api/spaces/main/picture", content=png()).status_code == 403
    assert leon.post("/api/spaces/main/archive", json={"archived": False}).status_code == 200
    assert row(pei, "main")["archived"] is False
    assert pei.post(f"/api/episodes/{EPISODE}/undo").status_code != 403


def test_lands_in_a_live_project_not_an_archived_one(tmp_path):
    ws, leon = setup(tmp_path)
    beta = join(leon, "beta@example.com")
    first = beta.get("/api/spaces").json()["current"]["id"]
    second = make(beta, "第二个")
    beta.post(f"/api/spaces/{first}/archive", json={"archived": True})
    fresh = type(beta)(beta.app)
    fresh.cookies = beta.cookies
    fresh.cookies.delete("lacuna_space")
    assert fresh.get("/api/spaces").json()["current"]["id"] in (second,)


def test_delete_for_good(tmp_path):
    ws, leon = setup(tmp_path)
    beta = join(leon, "beta@example.com")
    own = beta.get("/api/spaces").json()["current"]["id"]
    sid = make(beta, "要删的")
    folder = ws / "spaces" / sid
    (folder / "learning" / "asks").mkdir(parents=True)
    (folder / "learning" / "asks" / "ep1.json").write_text("{}", encoding="utf-8")
    (folder / "learning" / "rules.json").write_text("{}", encoding="utf-8")
    beta.post(f"/api/spaces/{sid}/picture", content=png())
    leon.post(f"/api/spaces/{sid}/members", json={"email": "leon@example.com", "role": "admin"})
    assert row(beta, sid)["can_delete"] is True
    assert row(beta, own)["can_delete"] is True
    assert row(leon, "main")["can_delete"] is True                 # the first show too (Leon 2026-10-24)
    # only from 已归档
    r = beta.request("DELETE", f"/api/spaces/{sid}", json={"confirm": "要删的"})
    assert r.status_code == 409
    pei = join(leon, "pei@example.com")
    beta.post(f"/api/spaces/{sid}/members", json={"email": "pei@example.com", "role": "admin"})
    beta.post(f"/api/spaces/{sid}/archive", json={"archived": True})
    # members can't be changed while archived
    assert beta.post(f"/api/spaces/{sid}/members", json={"email": "pei@example.com", "role": "viewer"}).status_code == 403
    # a manager who didn't create it may not delete it; the name must be typed exactly
    assert row(pei, sid)["can_delete"] is False
    assert pei.request("DELETE", f"/api/spaces/{sid}", json={"confirm": "要删的"}).status_code == 403
    assert beta.request("DELETE", f"/api/spaces/{sid}", json={"confirm": "要删"}).status_code == 422
    assert folder.is_dir()
    r = beta.request("DELETE", f"/api/spaces/{sid}", json={"confirm": "要删的"})
    assert r.status_code == 200 and r.json()["deleted"] == sid
    assert not folder.exists()
    assert sid not in [m["id"] for m in beta.get("/api/spaces").json()["mine"]]
    assert not (ws / "auth" / "pictures" / f"{sid}.png").exists()
    # what was learned in it is kept in the deleting person's own store (not the project's rules file)
    kept = list((habits.home_for(ws, "beta@example.com") / "learning" / "from_projects").iterdir())
    assert len(kept) == 1 and kept[0].name.startswith(sid)
    assert (kept[0] / "asks" / "ep1.json").is_file() and not (kept[0] / "rules.json").exists()


def test_cannot_delete_your_last_project(tmp_path):
    ws, leon = setup(tmp_path)
    beta = join(leon, "beta@example.com")
    own = beta.get("/api/spaces").json()["current"]["id"]
    beta.post(f"/api/spaces/{own}/archive", json={"archived": True})
    r = beta.request("DELETE", f"/api/spaces/{own}", json={"confirm": row(beta, own)["name"]})
    assert r.status_code == 409 and "唯一" in r.json()["detail"]


def test_owner_may_delete_anyones_project(tmp_path):
    ws, leon = setup(tmp_path)
    beta = join(leon, "beta@example.com")
    sid = make(beta, "别人的")
    beta.post(f"/api/spaces/{sid}/members", json={"email": "leon@example.com", "role": "viewer"})
    beta.post(f"/api/spaces/{sid}/archive", json={"archived": True})
    assert row(leon, sid)["can_delete"] is True
    assert leon.request("DELETE", f"/api/spaces/{sid}", json={"confirm": "别人的"}).status_code == 200
