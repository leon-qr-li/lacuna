"""English episodes (decision english-engine): the episode's language picks the recognisers, the
editor document's notes and the AI brief; English words are merged from sentencepiece pieces and
shown with spaces. ASR is faked like in test_import.py; the real Parakeet path is
tests/test_asr_en_real.py."""
import json
import shutil

import pytest

from lacuna_app import asr, features, first_cut, show
from lacuna_app.ai_cut import TrackTokens
from lacuna_app.episode import Episode
from lacuna_app.first_cut import ClaudeFirstCut
from lacuna_app.importer import ImportError_, Importer
from lacuna_app.store import Workspace
from lacuna_app.words import is_latin, join_words, needs_space

from .fake_claude import FakeFirstCutAnthropic
from .synth import fake_asr, write_recordings


# ---------------------------------------------------------------- words


def test_join_words_spaces_only_between_latin_words():
    assert join_words(["so", "first,", "of", "all."]) == "so first, of all."
    assert join_words(["我", "看", "了", "Netflix", "的"]) == "我看了Netflix的"
    assert join_words(["OK", "OK"]) == "OK OK"
    assert join_words(["a", ",", "b", "", "c"]) == "a, b c"
    assert join_words(["Hello there.", "Yes I", "did"]) == "Hello there. Yes I did"
    assert not needs_space("嗯", "OK") and not needs_space("so", "，")
    assert is_latin("experience,") and is_latin("we've") and not is_latin(",") and not is_latin("嗯")


def test_sentencepiece_pieces_become_words():
    pieces = [{"t": "▁Hi", "start": 0.0, "end": 0.2}, {"t": "▁exper", "start": 0.3, "end": 0.5},
              {"t": "ience", "start": 0.5, "end": 0.7}, {"t": ",", "start": 0.7, "end": 0.75},
              {"t": " we", "start": 0.9, "end": 1.0}, {"t": "'ve", "start": 1.0, "end": 1.1}, {"t": "▁", "start": 1.2, "end": 1.2}]
    assert asr.words_from_pieces(pieces) == [
        {"t": "Hi", "start": 0.0, "end": 0.2}, {"t": "experience,", "start": 0.3, "end": 0.75},
        {"t": "we've", "start": 0.9, "end": 1.1}]


def test_engines_per_language(tmp_path):
    assert asr.language("en") == "en" and asr.language("fr") == "zh" and asr.language(None) == "zh"
    en = {m[0] for m in asr.ENGINES["en"]}
    assert f"{asr.PARAKEET}/encoder.int8.onnx" in en and f"{asr.PARAFORMER}/model.int8.onnx" not in en
    for probe, _, _ in asr.ENGINES["zh"]:
        (tmp_path / probe).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / probe).write_bytes(b"x")
    assert asr.models_present(tmp_path, "zh") and not asr.models_present(tmp_path, "en")


# ---------------------------------------------------------------- features


def _seg(words, sv_words, a=0.0):
    toks = [{"t": w, "start": a + 0.3 * i, "end": a + 0.3 * i + 0.25} for i, w in enumerate(words)]
    sv = [{"t": w, "start": a + 0.3 * i, "end": a + 0.3 * i + 0.25} for i, w in enumerate(sv_words)]
    return {"start": a, "end": a + 0.3 * len(words), "par": {"text": " ".join(words), "tokens": toks},
            "sv": {"text": " ".join(sv_words), "event": "Speech", "emotion": "NEUTRAL", "tokens": sv}}


def test_case_and_punctuation_are_not_disagreements():
    import numpy as np
    x = (0.1 * np.sin(np.arange(16000 * 6) / 16000 * 2 * np.pi * 150)).astype(np.float32)
    a = {"audio_s": 6.0, "segments": [_seg(["Hi", "everyone,", "welcome", "to", "the", "the", "show."],
                                           ["hi", "everyone", "welcome", "to", "the", "show"])]}
    b = {"audio_s": 6.0, "segments": [_seg(["So,", "um,", "yeah."], ["so", "yeah"], 3.0)]}
    toks, feats, doc = features.build({"A": a, "B": b}, {"A": x, "B": x}, "EP9", log=lambda *_: None,
                                      names={"A": "Ana", "B": "Bo"}, show_name="Talk", lang="en")
    flagged = [t["t"] for t in toks["tracks"]["A"] if t["flag"]]
    assert flagged == ["the"]                      # only the real difference (the repeated "the")
    assert [t["t"] for t in toks["tracks"]["B"] if t["flag"]] == ["um,"]
    assert "The episode is in **English**" in doc and "A = Ana's track" in doc
    assert "Hi everyone, welcome to" in doc        # words spaced, punctuation kept
    assert "== floor gap" in doc and "== 地板间隙" not in doc


def test_chinese_document_unchanged_by_language_default():
    import numpy as np
    x = (0.1 * np.sin(np.arange(16000 * 3) / 16000 * 2 * np.pi * 150)).astype(np.float32)
    a = {"audio_s": 3.0, "segments": [_seg(["我", "觉", "得"], ["我", "觉", "得"])]}
    _, _, doc = features.build({"L": a}, {"L": x}, "EP9", log=lambda *_: None, names={"L": "Leon"})
    assert "## 格式说明" in doc and "@0 我觉得" in doc


def test_text_in_spaces_english_words():
    tt = TrackTokens([{"id": "A000000", "t": "so", "start": 0.0, "end": 0.2},
                      {"id": "A000001", "t": "first,", "start": 0.3, "end": 0.5},
                      {"id": "A000002", "t": "of", "start": 0.6, "end": 0.7}])
    assert tt.text_in(0.0, 1.0) == "so first, of"


# ---------------------------------------------------------------- AI brief


def test_english_brief_for_any_show():
    prof = show.normalise({"show_name": "Talk", "language": "en", "hosts": [{"name": "Ana"}, {"name": "Bo"}]},
                          strict=True, before=show.NEW)
    s = first_cut.system_prompt("", prof, "en")
    assert "This episode is in English" in s and "um, uh" in s and "Ana = track" in s
    assert "嗯" not in s and "我觉得" not in s and "<<" not in s
    # Leon's show, English episode: English brief with his hosts, not the EP001 (Chinese) calibration
    s = first_cut.system_prompt("- R1 keep pauses", show.LEGACY, "en")
    assert "This episode is in English" in s and "Leon = track L" in s and "R1 keep pauses" in s
    assert "EP001" not in s.split("RULES LEARNED")[0]
    # Chinese stays as it was
    assert first_cut.system_prompt("", show.LEGACY, "zh") == first_cut.system_prompt("", show.LEGACY)


def test_show_language_saved_and_defaulted(tmp_path):
    assert show.load(tmp_path)["language"] == "zh"
    p = show.save(tmp_path, {"show_name": "Talk", "language": "en", "hosts": [{"name": "Ana"}]})
    assert p["language"] == "en" and show.load(tmp_path)["language"] == "en"
    assert show.normalise({"language": "xx"}, strict=False)["language"] == "zh"
    assert "en" in show.view(p)["languages"]


# ---------------------------------------------------------------- import


EN = {"我": "So,", "觉": "I", "得": "think", "这": "the", "个": "movie", "电": "is", "影": "great."}


def english_asr(tag, x, progress=lambda f, s: None):
    """fake_asr with every Chinese character turned into an English word (main engine cased and
    punctuated, SenseVoice lower-case without punctuation, like the real pair)."""
    res = fake_asr(tag, x, progress)
    for seg in res["segments"]:
        for key in ("par", "sv"):
            for t in seg[key]["tokens"]:
                w = EN.get(t["t"], "yeah")
                t["t"] = w if key == "par" else w.lower().strip(",.")
            seg[key]["text"] = join_words(t["t"] for t in seg[key]["tokens"])
    return res


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_english_import(tmp_path):
    ws = Workspace(tmp_path / "ws").ensure()
    rec = write_recordings(tmp_path / "rec")
    show.write_new(ws.root)
    show.save(ws.root, {"show_name": "Talk", "language": "zh", "hosts": [{"name": "Ana"}, {"name": "Bo"}]})
    fake = FakeFirstCutAnthropic()
    imp = Importer(ws, first_cut_factory=lambda: ClaudeFirstCut(client=fake), asr_backend=english_asr)
    with pytest.raises(ImportError_):
        imp.start("EP002", "", [str(rec["Leon"]), str(rec["Pei"])], language="fr")
    tags = [h["tag"] for h in show.load(ws.root)["hosts"]]
    real = english_asr
    imp.asr_backend = lambda tag, x, p=lambda f, s: None: real({tags[0]: "L", tags[1]: "P"}[tag], x, p)
    imp.start("EP002", "", [str(rec["Leon"]), str(rec["Pei"])], wait=True, language="en")   # the form overrides the show
    job = imp.status("EP002")
    assert job["state"] == "done", job["error"]
    assert job["language"] == "en"
    ep = Episode(ws, "EP002")
    assert ep.meta["language"] == "en"
    req = fake.requests[0]
    assert "This episode is in English" in req["system"][0]["text"]
    assert "The episode is in **English**" in req["system"][1]["text"]
    words = json.loads((ws.root / "imports" / "EP002" / "tokens.json").read_text(encoding="utf-8"))
    assert any(t["t"] == "So," for t in words["tracks"][tags[0]])
    ep.close()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_import_language_defaults_to_the_shows(tmp_path):
    ws = Workspace(tmp_path / "ws").ensure()
    rec = write_recordings(tmp_path / "rec")
    imp = Importer(ws, first_cut_factory=lambda: ClaudeFirstCut(client=FakeFirstCutAnthropic()), asr_backend=fake_asr)
    job = imp.start("EP002", "", [str(rec["Leon"]), str(rec["Pei"])], wait=True)     # Leon's show: zh
    assert job["language"] == "zh" and imp.status("EP002")["state"] == "done"


def test_show_api_keeps_the_language(tmp_path):
    from fastapi.testclient import TestClient
    from lacuna_app import create_app
    from lacuna_app.editor import MockEditorAdapter
    from .synth import make_workspace
    c = TestClient(create_app(make_workspace(tmp_path / "ws"), MockEditorAdapter(), web_dist=tmp_path / "none"))
    assert c.get("/api/show").json()["language"] == "zh"
    body = c.get("/api/show").json() | {"language": "en"}
    assert c.put("/api/show", json=body).json()["language"] == "en"
    assert c.get("/api/show").json()["language"] == "en"


# ---------------------------------------------------------------- dropped fillers


def test_is_filler():
    assert features.is_filler("Uh") and features.is_filler("Um.") and features.is_filler("uh, um")
    assert not features.is_filler("Mm.") and not features.is_filler("Hmm.") and not features.is_filler("Yeah.")
    assert not features.is_filler("") and not features.is_filler("Uh, so")


def test_sounds_without_words_are_heard_again():
    import numpy as np
    sr = 16000
    t = np.arange(sr * 6) / sr
    x = np.zeros(len(t), np.float32)
    x[int(0.5 * sr):int(1.4 * sr)] = 0.1 * np.sin(2 * np.pi * 150 * t[int(0.5 * sr):int(1.4 * sr)])   # "So I"
    x[int(1.8 * sr):int(2.2 * sr)] = 0.1 * np.sin(2 * np.pi * 120 * t[int(1.8 * sr):int(2.2 * sr)])   # an um
    x[int(2.8 * sr):int(3.7 * sr)] = 0.1 * np.sin(2 * np.pi * 150 * t[int(2.8 * sr):int(3.7 * sr)])   # "think so."
    x[int(4.5 * sr):int(4.8 * sr)] = 0.1 * np.sin(2 * np.pi * 200 * t[int(4.5 * sr):int(4.8 * sr)])   # a "yeah"
    x += 1e-4 * np.random.default_rng(0).standard_normal(len(x)).astype(np.float32)
    seg = {"start": 0.4, "end": 3.8, "par": {"text": "So I think so.", "tokens": [
        {"t": "So", "start": 0.5, "end": 0.9}, {"t": "I", "start": 1.0, "end": 1.4},
        {"t": "think", "start": 2.8, "end": 3.2}, {"t": "so.", "start": 3.3, "end": 3.7}]},
           "sv": {"text": "so i think so", "event": "Speech", "emotion": "NEUTRAL", "tokens": [
        {"t": "so", "start": 0.5, "end": 0.9}, {"t": "i", "start": 1.0, "end": 1.4},
        {"t": "think", "start": 2.8, "end": 3.2}, {"t": "so", "start": 3.3, "end": 3.7}]}}
    asked = []

    def hear(clips):
        asked.extend(clips)
        return ["Um" if a < 3 else "Yeah." for _, a, _ in clips]

    _, feats, doc = features.build({"A": {"audio_s": 6.0, "segments": [seg]}}, {"A": x}, "E", log=lambda *_: None,
                                   names={"A": "Ana"}, lang="en", hear=hear)
    assert [round(a, 1) for _, a, _ in asked] == [1.8, 4.5]
    assert feats["stats"]["filler_candidates"] == 1
    assert '~filler 0.4' in doc and 'heard "Um"' in doc and '~snd 0.3' in doc and 'heard "Yeah."' in doc
    assert "~filler) @" in doc, doc              # the pause inside "So I … think so." holds it
    _, _, zh = features.build({"A": {"audio_s": 6.0, "segments": [seg]}}, {"A": x}, "E", log=lambda *_: None,
                              names={"A": "Ana"})
    assert "~filler" not in zh and "heard" not in zh


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_english_import_listens_for_fillers(tmp_path):
    ws = Workspace(tmp_path / "ws").ensure()
    rec = write_recordings(tmp_path / "rec")
    show.write_new(ws.root)
    show.save(ws.root, {"show_name": "Talk", "language": "en", "hosts": [{"name": "Ana"}, {"name": "Bo"}]})
    tags = [h["tag"] for h in show.load(ws.root)["hosts"]]
    imp = Importer(ws, first_cut_factory=lambda: ClaudeFirstCut(client=FakeFirstCutAnthropic()),
                   asr_backend=lambda tag, x, p=lambda f, s: None: english_asr({tags[0]: "L", tags[1]: "P"}[tag], x, p))
    heard, calls = [], []
    imp.hear_backend = lambda audio: (lambda clips: calls.append(set(audio)) or heard.extend(clips) or ["Uh"] * len(clips))
    imp.start("EP002", "", [str(rec["Leon"]), str(rec["Pei"])], wait=True)
    job = imp.status("EP002")
    assert job["state"] == "done", job["error"]
    assert job["language"] == "en" and calls == [set(tags)]
    assert job["steps"]["features"]["fillers"] == len(heard)
