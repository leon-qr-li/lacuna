"""Backlog item 8: erase one host's sound and fill it with that track's own room tone, from the AI
first cut and from the editing chat ("抹掉 Pei 那个嗯")."""
import numpy as np
import pytest

from lacuna_app import Episode, Workspace
from lacuna_app.episode import APPLIED, RESTORED

from .synth import AI_EPISODE, SR, make_ai_workspace
from .test_claude_chat import EP, FakeClient, act, answer, app_with, tool_response


@pytest.fixture
def ws(tmp_path):
    return make_ai_workspace(tmp_path / "ws")


def pei_level(ep: Episode, enabled, a: float, b: float) -> float:
    tl = ep.timeline_for(enabled)
    i = [t.name for t in tl.tracks].index("Pei")
    y = ep.previewer.renderer.render_track(tl, i, int(a * SR), int(b * SR))
    return float(np.sqrt(np.mean(y ** 2)))


def test_first_cut_single_track_cut_is_an_erase_with_room_tone(ws):
    ep = Episode(Workspace(ws), AI_EPISODE)
    e = next(e for e in ep.edits.values() if any(o["op"] == "erase" for o in e.ops))
    o = e.ops[0]
    assert o["track"] == "Pei" and o["tone_media_id"] in ep.media
    assert o["tone_src_out"] - o["tone_src_in"] >= int(0.3 * SR)
    # the tone is Pei's own quiet room, nowhere near any of her words
    words = [(s, en) for trk, s, en, _ in ep.words(0, 1e9) if trk == "Pei"]
    clip = ep.base.track("Pei").clips[0]                 # base = raw minus the window start
    ta, tb = ((o[k] - clip.src_in + clip.start) / SR for k in ("tone_src_in", "tone_src_out"))
    assert not any(s < tb and en > ta for s, en in words)
    assert e.tracks == ["Pei"]
    j = next(d for d in ep.summary()["edits"] if d["id"] == e.id)
    assert j["room_tone"] is True and j["tracks"] == ["Pei"]
    # the erased span sounds like the room
    cuts = ep.cuts_for(ep.enabled)
    from lacuna_app.episode import to_tl
    a, b = to_tl(o["start"], cuts) / SR, to_tl(o["end"], cuts) / SR
    level = pei_level(ep, ep.enabled, a + 0.03, b - 0.03)
    assert 1e-4 < level < 1e-3                       # synth room is 3e-4 rms; Pei's speech would be ~0.1
    ep.close()


def test_chat_cut_one_track_erases_with_room_tone_and_can_be_restored(ws):
    def pei_only(sc):
        u = next(u for u in sc["utterances"] if u["speaker"] == "Pei" and u["start"] > 30)
        return tool_response(answer([act("cut_one_track", from_utterance=u["id"], end_text=u["text"][:2])],
                                    category="interjection", title="抹掉 Pei 的嗯"))
    fake = FakeClient(pei_only)
    client = app_with(ws, fake)
    d0 = client.get(EP).json()["duration"]
    r = client.post(f"{EP}/chat", json={"text": "抹掉 Pei 这两个嗯", "playhead": 36.0}).json()
    assert "room tone" in str(fake.requests[-1]["system"])        # the model knows nothing goes silent
    s = client.post(f"{EP}/proposals/{r['proposal']['id']}/approve", json={}).json()
    e = next(e for e in s["edits"] if e["source"] == "chat")
    assert e["tracks"] == ["Pei"] and e["room_tone"] and s["duration"] == pytest.approx(d0)   # nothing moved
    ab = client.get(f"{EP}/edits/{e['id']}/ab").json()
    assert ab["before"]["duration"] == pytest.approx(ab["after"]["duration"], abs=1e-3)

    ep = Episode(Workspace(ws), AI_EPISODE)
    ed = ep.edits[e["id"]]
    assert ed.ops[0]["op"] == "erase" and ed.ops[0]["tone_media_id"]
    t0, t1 = e["t"], e["t"] + e["len"]
    erased = pei_level(ep, ep.enabled, t0 + 0.05, t1 - 0.05)
    original = pei_level(ep, ep.enabled - {ed.id}, t0 + 0.05, t1 - 0.05)
    assert erased < 1e-3 < original                 # her words are gone, the room stays
    assert erased > 1e-4                            # ... and it is not a hole of digital silence
    ep.close()

    s = client.post(f"{EP}/edits/{e['id']}/review", json={"action": "restore"}).json()
    assert next(x for x in s["edits"] if x["id"] == e["id"])["status"] == RESTORED
    s = client.post(f"{EP}/undo", json={}).json()
    assert next(x for x in s["edits"] if x["id"] == e["id"])["status"] == APPLIED


def test_old_lifts_still_open_and_render(ws):
    # episodes saved before this change hold plain lifts; they keep working unchanged
    ep = Episode(Workspace(ws), AI_EPISODE)
    e = next(e for e in ep.edits.values() if any(o["op"] == "erase" for o in e.ops))
    e.ops = [{"op": "lift", "track": o["track"], "start": o["start"], "end": o["end"]} for o in e.ops]
    ep.save()
    ep.close()
    ep = Episode(Workspace(ws), AI_EPISODE)
    assert ep.edits[e.id].ops[0]["op"] == "lift" and ep.summary()["duration"] > 0
    ep.close()
