"""A new account's first show, before its first visit names it, is called 「新节目」 everywhere
(the show switcher, the project list), never their email address (lacuna_app/spaces.py title)."""
from __future__ import annotations

from lacuna_app import i18n
from tests.app.test_spaces import join, setup


def current(c):
    return c.get("/api/spaces").json()["current"]


def test_first_show_is_new_show_until_named(tmp_path):
    ws, leon = setup(tmp_path)
    beta = join(leon, "someone.long.name@example.com")
    sp = beta.get("/api/spaces").json()
    assert sp["current"]["name"] == "新节目"
    assert [m["name"] for m in sp["mine"]] == ["新节目"]
    assert all("someone" not in s["name"] for s in [sp["current"], *sp["mine"], *sp["all"]])
    beta.cookies.set("lacuna_lang", "en")
    assert current(beta)["name"] == "New show"
    tok = i18n.set_request_lang("zh")      # the request above left "en" as this thread's language
    i18n.reset_request_lang(tok)
    beta.cookies.set("lacuna_lang", "zh")
    assert beta.put("/api/show", json={"show_name": "周末电影院", "hosts": [{"name": "Ana"}]}).status_code == 200
    assert current(beta)["name"] == "周末电影院"


def test_a_show_made_with_a_name_keeps_it(tmp_path):
    ws, leon = setup(tmp_path)
    beta = join(leon, "beta@example.com")
    sid = beta.post("/api/spaces", json={"name": "片场夜谈"}).json()["created"]
    names = {m["id"]: m["name"] for m in beta.get("/api/spaces").json()["mine"]}
    assert names[sid] == "片场夜谈"
    assert current(leon)["name"] == "洛城二三事"          # older shows unchanged
