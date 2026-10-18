"""Episode.words bisects a per-track index instead of scanning the whole transcript; the answer
must be exactly the scan's (learning, the edit text and the chat context all read it)."""
import numpy as np

from lacuna_app.episode import Episode
from lacuna_app.store import Workspace

from .synth import EPISODE, make_workspace


def scan(transcript, a_s, b_s):
    out = []
    for track, words in transcript["tracks"].items():
        out += [(track, s, e, w) for s, e, w in words if e > a_s and s < b_s]
    return sorted(out, key=lambda x: x[1])


def test_words_match_a_full_scan(tmp_path):
    make_workspace(tmp_path)
    ep = Episode(Workspace(tmp_path), EPISODE)
    rng = np.random.default_rng(3)
    long_word = [[0.4, 30.0, "长"]]                      # spans many later starts: the running max end matters
    ep.transcript["tracks"]["Leon"] = long_word + ep.transcript["tracks"]["Leon"]
    shuffled = list(ep.transcript["tracks"]["Pei"])
    rng.shuffle(shuffled)                                   # out of order: falls back to the scan
    ep.transcript["tracks"]["Gast"] = shuffled
    ep._words_ix = None
    ix = {t: starts for t, _, starts, _ in ep._word_index()}
    assert ix["Leon"] is not None and ix["Pei"] is not None and ix["Gast"] is None
    probes = [(a, a + w) for a in rng.uniform(-5, 65, 300) for w in (0.0, 0.01, 0.3, 4.0, 80.0)]
    probes += [(0.5, 0.75), (0.75, 0.8), (30.0, 30.0), (-1.0, 0.0)]
    for a, b in probes:
        assert ep.words(a, b) == scan(ep.transcript, a, b), (a, b)
    assert ep.words(0, 100)
    ep.close()
