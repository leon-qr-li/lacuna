"""Second full scan (2026-10-18, batch V1-V10): bugs found where this batch's changes meet."""
import json

import numpy as np

from lacuna_app import room_tone
from lacuna_app.episode import Episode
from lacuna_app.lessons import NoAnswer, ai_failure

from .synth import SR
from .test_full_scan_audio import EP, one_track_workspace


def test_an_episode_opens_even_if_the_room_tone_repair_fails(tmp_path, monkeypatch):
    """V5 repairs old room tone while the episode opens; a read error there (a source file that
    can't be read right now) must not make the episode impossible to open."""
    rng = np.random.default_rng(3)
    ws = one_track_workspace(tmp_path, "Pei", 0.2 * rng.standard_normal(120 * SR))
    ep = Episode(ws, EP)
    media = next(iter(ep.media))
    ep.close()
    bad = {"op": "erase", "track": "Pei", "start": 100 * SR, "end": int(100.5 * SR),
           "tone_media_id": media, "tone_src_in": 5 * SR, "tone_src_out": int(5.5 * SR)}
    p = ws.episode_dir(EP) / "state.json"
    st = json.loads(p.read_text(encoding="utf-8"))
    st["edits"] = [{"id": "e1", "ops": [bad], "category": "interjection", "title": "t", "reason": "",
                    "confidence": 0.9, "consequential": True, "status": "applied", "source": "ai"}]
    p.write_text(json.dumps(st), encoding="utf-8")

    def broken(self):
        raise OSError("source busy")
    monkeypatch.setattr(Episode, "fill_room_tone", broken)
    ep = Episode(ws, EP)                       # opens
    assert room_tone.misplaced(ep.edits["e1"].ops[0], ep.base)   # untouched, tried again next time
    ep.close()
    monkeypatch.undo()
    ep = Episode(ws, EP)
    assert not room_tone.misplaced(ep.edits["e1"].ops[0], ep.base)
    ep.close()


def test_no_answer_message_reads_well_inside_the_rewrite_notice():
    """The card says 「这次没能改写（…）」; the reason must not repeat 这次."""
    msg = ai_failure(NoAnswer("end_turn"))
    assert msg == "LACUNA 没有给出结果" and "这次" not in msg
