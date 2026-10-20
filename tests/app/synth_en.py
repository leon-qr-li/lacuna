"""The synthetic workspace's episode as an English one with um / uh (decision `english-fillers`), for
tests/app/test_fillers.py and the E2E server (tests/app/e2e/fillers.py)."""
from __future__ import annotations

import json
from pathlib import Path

from lacuna_app.fillers import merge

from .synth import make_workspace, words_by_track

EN_EPISODE = "EP_TEST_English"
EN_TITLE = "English test (um / uh)"
WORDS = "so I think the movie is really great you know and then the ending".split()
# fillers the recogniser wrote (the word at that start time becomes it) ...
WRITTEN = {("Leon", 0.5): "Um,", ("Pei", 31.0): "uh"}
# ... and the ones it dropped, found by listening again (features.build `hear`): (track tag, start, end, heard)
DETECTED = [("L", 16.4, 16.75, "Uh."),     # nobody else talks: cut from every track
            ("L", 6.2, 6.5, "Um"),         # under Pei's turn (5.5-8.0): only Leon is silenced
            ("P", 45.0, 45.3, "Uh")]       # inside an AI pause cut (44.3-45.7): already gone


def make_en_workspace(root: str | Path, episode_id: str = EN_EPISODE) -> Path:
    root = Path(make_workspace(root, episode_id))
    d = root / "episodes" / episode_id
    meta = json.loads((d / "episode.json").read_text(encoding="utf-8"))
    meta.update(title=EN_TITLE, language="en", demo=False)
    (d / "episode.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    tracks = {}
    for name, ws in words_by_track().items():
        tracks[name] = [[s, e, WRITTEN.get((name, s), WORDS[i % len(WORDS)])] for i, (s, e, _) in enumerate(ws)]
    sounds = [{"track": t, "start": a, "end": b, "heard": h, "filler": True, "src": "energy"} for t, a, b, h in DETECTED]
    sounds.append({"track": "P", "start": 17.0, "end": 17.3, "heard": "Yeah.", "filler": False, "src": "energy"})
    transcript = merge({"tracks": tracks}, sounds, {"L": "Leon", "P": "Pei"})
    (d / meta.get("transcript", "transcript.json")).write_text(json.dumps(transcript), encoding="utf-8")
    return root
