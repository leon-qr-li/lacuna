"""Music placed by use, suggestions heard before they are accepted, and music changed by talking."""
import shutil

import pytest

from lacuna_app.episode import ConflictError, Episode
from lacuna_app.library import Library
from lacuna_app.music import EpisodeMusic
from lacuna_app.music_assist import MusicChat, apply_actions, auto_place, break_candidates, pauses, snap
from lacuna_app.store import Workspace

from .fake_music import FakeMusicAnthropic
from .synth import EPISODE, SR, make_workspace, write_music

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


@pytest.fixture
def ws(tmp_path):
    return Workspace(make_workspace(tmp_path / "ws"))


@pytest.fixture
def ep(ws):
    e = Episode(ws, EPISODE)
    yield e
    e.close()


@pytest.fixture
def lib(ws, tmp_path):
    lib = Library(ws)
    for name, kind, secs in (("intro.wav", "intro", 8.0), ("mid.wav", "interlude", 6.0),
                             ("end.wav", "outro", 10.0), ("bed.wav", "bed", 20.0)):
        lib.add_file(write_music(tmp_path / "in" / name, secs, stereo=False), kind)
    return lib


def by_role(lib):
    return {a["kind"]: a for a in lib.assets()}


def test_pauses_and_snap(ws, ep, lib):
    m = EpisodeMusic(ws, ep, lib)
    ps = pauses(m)
    assert ps and all(n >= 0.3 for _, n in ps)
    t, _ = max(ps, key=lambda x: x[1])
    assert snap(m, t + 1.5) == pytest.approx(t, abs=0.01)
    assert snap(m, -100.0) == -100.0          # nothing nearby: unchanged
    voice = ep.timeline_for(ep.enabled).length / SR
    cands = break_candidates(m)
    assert cands and all(0.2 * voice <= c <= 0.9 * voice for c in cands)


def test_auto_place_is_a_suggestion_until_accepted(ws, ep, lib):
    m = EpisodeMusic(ws, ep, lib)
    key0 = m.export_key()
    out = auto_place(m)
    d = out["draft"]
    assert [c["kind"] for c in d["changes"]] == ["add", "add", "add"]
    assert sorted(p["role"] for p in d["placements"]) == ["interlude", "intro", "outro"]
    assert "铺底背景音" in out["message"] or "背景" in out["message"]     # the bed is left to Leon
    # nothing changed in the real music yet: the export is not stale, the summary lists no placements
    assert m.placements() == [] and m.export_key() == key0 and m.summary()["placements"] == []
    # the suggestion can be heard: the preview of its interlude renders
    mid = next(p for p in d["placements"] if p["role"] == "interlude")
    wav, start = m.preview(mid["id"], placements=m.draft()["placements"])
    assert wav[:4] == b"RIFF" and start >= 0
    # interlude sits in a pause
    assert any(abs(mid["voice_at_s"] - t) < 0.01 for t, _ in pauses(m))
    # another offered position can be picked
    alts = d["alternatives"].get(mid["id"]) or []
    if alts:
        m.move_draft(mid["id"], alts[0]["voice_s"])
        moved = next(p for p in m.draft_view()["placements"] if p["id"] == mid["id"])
        assert moved["voice_at_s"] == pytest.approx(alts[0]["voice_s"], abs=0.01)
    m.accept_draft(d["id"])
    assert sorted(p["role"] for p in m.placements()) == ["interlude", "intro", "outro"]
    assert m.draft() is None and m.export_key() != key0
    # again: everything that can be placed by use is already there
    again = auto_place(m)
    assert again["draft"] is None and "都已经放好" in again["message"]


def test_stale_and_discarded_suggestions(ws, ep, lib):
    m = EpisodeMusic(ws, ep, lib)
    d = auto_place(m)["draft"]
    m.add(by_role(lib)["intro"]["id"], "intro")             # the music changed after the suggestion
    assert m.draft_view()["stale"]
    with pytest.raises(ConflictError):
        m.accept_draft(d["id"])
    with pytest.raises(KeyError):
        m.accept_draft("dr_nope")
    m.discard_draft()
    assert m.draft() is None and len(m.placements()) == 1


def test_actions_move_set_remove_add(ws, ep, lib):
    m = EpisodeMusic(ws, ep, lib)
    a = by_role(lib)
    m.add(a["intro"]["id"], "intro", overlap_s=2.0)
    mid = m.add(a["interlude"]["id"], "interlude", at_s=20.0)
    m.add(a["outro"]["id"], "outro")
    lay = m.layout()
    at = next(it.anchor for it in lay.items if it.p["id"] == mid["id"]) / SR

    def act(type_, **kw):
        return {"type": type_, **kw}

    ps, ch = apply_actions(m, [act("move", placement_id=mid["id"], shift_s=2.0)])
    new = m.layout(placements=ps)
    at2 = next(it.anchor for it in new.items if it.p["id"] == mid["id"]) / SR
    # roughly two seconds later (snapped to a pause), and the change reads like Leon would say it
    assert 0 < at2 - at < 2.0 + 4.1 and ch[0]["kind"] == "move" and "间奏" in ch[0]["text"]
    ps, ch = apply_actions(m, [act("set", placement_id=mid["id"], gain_change_db=-3.0, overlap_s=1.5)])
    assert next(p for p in ps if p["id"] == mid["id"])["gain_db"] == -3.0
    assert ch[0]["text"] == "间奏：音量 -3 dB，和人声重叠 1.5 秒"
    outro = next(p for p in m.placements() if p["role"] == "outro")
    ps, ch = apply_actions(m, [act("remove", placement_id=outro["id"])])
    assert "outro" not in {p["role"] for p in ps} and ch[0]["text"] == "去掉片尾"
    ps, ch = apply_actions(m, [act("add", asset_id=a["bed"]["id"], role="bed", at_s=10.0, until_s=30.0)])
    assert any(p["role"] == "bed" and p["until_base"] is not None for p in ps)
    # the real music is untouched by any of this
    assert len(m.placements()) == 3
    for bad in ([act("move", placement_id="mu_nope", shift_s=1)],
                [act("move", placement_id=outro["id"], shift_s=1)],          # outro has no free position
                [act("add", asset_id=a["bed"]["id"], role="bed")],           # bed needs a position
                [act("set", placement_id=mid["id"])],
                [act("dance", placement_id=mid["id"])]):
        with pytest.raises(ValueError):
            apply_actions(m, bad)


def test_chat_makes_a_suggestion(ws, ep, lib):
    m = EpisodeMusic(ws, ep, lib)
    a = by_role(lib)
    mid = m.add(a["interlude"]["id"], "interlude", at_s=20.0)
    fake = FakeMusicAnthropic()
    chat = MusicChat(fake)
    out = chat.ask(m, "背景音小 3 dB 间奏")
    assert out["draft"] and out["usage"]["input_tokens"] == 1500
    assert next(p for p in out["draft"]["placements"] if p["id"] == mid["id"])["gain_db"] == -3.0
    assert m.placements()[0]["gain_db"] == 0.0                  # not applied until accepted
    sent = fake.calls[0]
    assert sent["tool_choice"]["name"] == "arrange_music" and "间奏" in sent["messages"][0]["content"]
    assert "talk_nearby" in sent["messages"][0]["content"]       # text only: no audio leaves the machine
    # nothing to change -> a question, no suggestion
    out = MusicChat(FakeMusicAnthropic(lambda c: {"message": "放哪一首？", "actions": []})).ask(m, "加点音乐")
    assert out["draft"] is None and out["message"] == "放哪一首？"
    # an impossible action -> explained, no suggestion
    bad = {"type": "remove", "placement_id": "mu_nope"}
    out = MusicChat(FakeMusicAnthropic(lambda c: {"message": "好", "actions": [bad]})).ask(m, "去掉")
    assert out["draft"] is None and "没法照做" in out["message"]


def test_export_key_ignores_suggestions_and_ui_fields(ws, ep, lib):
    m = EpisodeMusic(ws, ep, lib)
    a = by_role(lib)
    p = m.add(a["intro"]["id"], "intro")
    k = m.export_key()
    auto_place(m)
    assert m.export_key() == k
    m.update(p["id"], gain_db=-2.0)
    assert m.export_key() != k
