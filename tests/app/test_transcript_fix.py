"""Transcript proofreading against the show's names (decision `transcript-terms`): only reference terms,
only whole words, times kept; names corrected before apply without the model; any failure leaves the
text as heard; imports and episodes imported before both get it."""
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from lacuna_app import create_app, show
from lacuna_app import transcript_fix as tf
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.first_cut import ClaudeFirstCut
from lacuna_app.importer import Importer
from lacuna_app.publish import add_name
from lacuna_app.store import Workspace

from .fake_claude import FakeFirstCutAnthropic
from .synth import EPISODE, fake_asr, make_workspace, words_by_track, write_recordings

ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


class FakeMessages:
    """Answers with fixes from `answer(lines)`; lines are "L0001 Leon：text"."""

    def __init__(self, answer=lambda lines: [], error=None):
        self.answer, self.error, self.calls = answer, error, []

    def create(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        doc = json.loads(kw["messages"][0]["content"])
        fixes = self.answer(doc["lines"])
        return SimpleNamespace(stop_reason="end_turn", model="claude-sonnet-5-5",
                               usage=SimpleNamespace(input_tokens=1000, output_tokens=50),
                               content=[SimpleNamespace(type="text", text=json.dumps({"fixes": fixes}, ensure_ascii=False))])


def fixer(**kw):
    m = FakeMessages(**kw)
    return tf.TranscriptFixer(client=SimpleNamespace(messages=m)), m


def find(word):
    """An answer that reports `word` wherever a line has it."""
    def answer(lines, word=word):
        return [{"line": ln.split(" ", 1)[0], "wrong": w, "right": r}
                for ln in lines for w, r in word if w in ln.split("：", 1)[1].replace(" ", "")]
    return answer


def words(*texts, t0=0.0):
    return [{"t": t, "start": round(t0 + i * 0.3, 2), "end": round(t0 + i * 0.3 + 0.25, 2)} for i, t in enumerate(texts)]


def test_name_heard_as_two_characters_becomes_one_word_over_their_times():
    w = words("我", "是", "利", "奥")
    assert tf.replace(w, "利奥", "Leon") == 1
    assert [x["t"] for x in w] == ["我", "是", "Leon"]
    assert w[2]["start"] == 0.6 and w[2]["end"] == 1.15        # first word's start, last word's end


def test_same_length_chinese_term_is_fixed_character_for_character():
    w = words("洛", "城", "二", "三", "世")
    tf.replace(w, "洛城二三世", "洛城二三事")
    assert [x["t"] for x in w] == list("洛城二三事")
    assert [x["start"] for x in w] == [0.0, 0.3, 0.6, 0.9, 1.2]


def test_english_word_keeps_its_punctuation_and_never_splits_a_longer_word():
    w = words("this", "is", "pose,", "on", "purpose")
    assert tf.replace(w, "pose", "PULSE") == 1
    assert [x["t"] for x in w] == ["this", "is", "PULSE,", "on", "purpose"]
    assert tf.find_spans(words("purpose"), "pose") == []


def glossary(**kw):
    return tf.Glossary(**({"terms": ["洛城二三事", "Leon", "Pei", "PULSE"], "show": "洛城二三事"} | kw))


def test_only_reference_terms_quoted_from_the_line_survive():
    lines = [tf.Line("L0001", "Leon", words("我", "是", "利", "奥")),
             tf.Line("L0002", "Pei", words("这", "期", "又", "是", "一", "期", "pose"))]
    got = tf.check([{"line": "L0001", "wrong": "利奥", "right": "Leon"},
                    {"line": "L0002", "wrong": "pose", "right": "pulse"},        # spelled as the term
                    {"line": "L0001", "wrong": "我是", "right": "我们"},          # not a term
                    {"line": "L0002", "wrong": "利奥", "right": "Leon"},          # not in that line
                    {"line": "L0009", "wrong": "利奥", "right": "Leon"},          # no such line
                    {"line": "L0001", "wrong": "我是利奥" * 5, "right": "Leon"}], lines, glossary())
    assert got == [{"line": "L0001", "wrong": "利奥", "right": "Leon"},
                   {"line": "L0002", "wrong": "pose", "right": "PULSE"}]


def test_glossary_from_project_settings_names_and_title(tmp_path):
    root = tmp_path / "ws"
    Workspace(root).ensure()
    p = dict(show.LEGACY, legacy=False, show_name="洛城二三事", terms=["王家卫", " 花样年华 ", "王家卫", ""])
    assert show.save(root, p)["terms"] == ["王家卫", "花样年华"]
    p.pop("terms")
    assert show.save(root, p)["terms"] == ["王家卫", "花样年华"]       # a form without the field keeps them
    add_name(Workspace(root), "王家位", "王家卫")
    (root / "albums.json").write_text(json.dumps({"schema": 1, "albums": [{"id": "a1", "name": "脉动"}]}), encoding="utf-8")
    g = tf.glossary_for(root, "PULSE-013 · 花样年华", ["Pei"])
    assert g.terms[:3] == ["洛城二三事", "Leon", "Pei"]
    assert {"PULSE", "脉动", "王家卫", "花样年华"} <= set(g.terms)
    assert g.corrections == [{"wrong": "王家位", "right": "王家卫"}] and g.title == "PULSE-013 · 花样年华"


def test_names_corrected_before_apply_without_the_model():
    lines = [tf.Line("L0001", "Leon", words("王", "家", "位", "的", "电", "影"))]
    g = glossary(corrections=[{"wrong": "王家位", "right": "王家卫"}])
    done = tf.TranscriptFixer(api_key="").fix(lines, g)
    assert lines[0].text == "王家卫的电影" and done[0]["right"] == "王家卫"


def test_a_failing_model_changes_nothing():
    fx, m = fixer(error=TimeoutError())
    lines = [tf.Line("L0001", "Leon", words("我", "是", "利", "奥"))]
    assert fx.fix(lines, glossary()) == [] and lines[0].text == "我是利奥" and m.calls


def test_off_switch(monkeypatch):
    monkeypatch.setenv("LACUNA_TRANSCRIPT_FIX", "off")
    fx, m = fixer(answer=find([("利奥", "Leon")]))
    lines = [tf.Line("L0001", "Leon", words("我", "是", "利", "奥"))]
    assert fx.fix(lines, glossary()) == [] and not m.calls


def test_long_transcripts_go_in_several_requests():
    lines = [tf.Line(f"L{i:04d}", "Leon", words(*"我们今天聊一部电影真的很好看")) for i in range(1, 1001)]
    fx, m = fixer()
    fx.fix(lines, glossary())
    assert len(m.calls) == len(tf.chunks(lines)) > 1
    sent = [json.loads(c["messages"][0]["content"]) for c in m.calls]
    assert sum(len(s["lines"]) for s in sent) == 1000 and sent[0]["terms"] == glossary().terms
    assert "audio" not in json.dumps(sent)


# ---------------------------------------------------------------------------- import

def misheard_asr(tag, x, progress=lambda f, s: None):
    """fake_asr, but Leon's first two words come out as 利奥 (and SenseVoice hears the same)."""
    res = fake_asr(tag, x, progress)
    if tag == "L":
        seg = res["segments"][0]
        for k in ("par", "sv"):
            toks = seg[k]["tokens"]
            toks[0]["t"], toks[1]["t"] = "利", "奥"
            seg[k]["text"] = "".join(t["t"] for t in toks)
    return res


@ffmpeg
def test_import_fixes_the_names_before_the_first_cut(tmp_path):
    ws = Workspace(tmp_path / "ws").ensure()
    rec = write_recordings(tmp_path / "in")
    fx, m = fixer(answer=lambda lines: find([("利奥", "Leon")])(lines) + [{"line": "L0001", "wrong": "利奥", "right": "随便"}])
    first = FakeFirstCutAnthropic()
    imp = Importer(ws, first_cut_factory=lambda: ClaudeFirstCut(client=first), asr_backend=misheard_asr)
    imp.term_fixer = fx
    job = imp.start("EP002", "EP002 · 测试", [str(rec["Leon"]), str(rec["Pei"])], wait=True)
    assert job["state"] == "done", job["error"]
    assert imp.status("EP002")["steps"]["terms"]["fixes"] == [{"wrong": "利奥", "right": "Leon", "count": 1}]
    d = ws.root / "imports" / "EP002"
    assert json.loads((d / "term_fixes.json").read_text(encoding="utf-8"))["fixes"] == \
        [{"line": "L0001", "wrong": "利奥", "right": "Leon"}]
    # the raw recognition stays as heard; the editor document and the transcript read Leon
    assert json.loads((d / "asr_L.json").read_text(encoding="utf-8"))["segments"][0]["par"]["tokens"][0]["t"] == "利"
    assert "利奥" not in (d / "editor_input.md").read_text(encoding="utf-8")
    t = json.loads((ws.episode_dir("EP002") / "transcript.json").read_text(encoding="utf-8"))
    first_words = sorted(t["tracks"]["Leon"])[:2]
    orig = words_by_track()["Leon"]
    assert first_words[0][2] == "Leon" and first_words[0][0] == pytest.approx(orig[0][0], abs=0.2)
    assert first_words[1][2] == orig[2][2]
    usage = [json.loads(x) for x in (ws.root / "ai_usage.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(u["kind"] == "transcript_fix" and u["episode"] == "EP002" for u in usage)
    assert "利奥" not in first.requests[0]["system"][1]["text"]
    # the new episode counts as proofread with today's terms: opening it asks nothing more
    g = tf.glossary_for(ws.root, "EP002 · 测试", ["Leon", "Pei"])
    assert tf.checked(ws.episode_dir("EP002")) == tf.signature(g)


@ffmpeg
def test_import_without_ai_keeps_the_text_as_heard(tmp_path):
    ws = Workspace(tmp_path / "ws").ensure()
    rec = write_recordings(tmp_path / "in")
    imp = Importer(ws, first_cut_factory=lambda: ClaudeFirstCut(client=FakeFirstCutAnthropic()), asr_backend=misheard_asr)
    imp.term_fixer = tf.TranscriptFixer(api_key="")
    job = imp.start("EP002", "EP002 · 测试", [str(rec["Leon"]), str(rec["Pei"])], wait=True)
    assert job["state"] == "done", job["error"]
    assert "terms" not in imp.status("EP002")["steps"]
    t = json.loads((ws.episode_dir("EP002") / "transcript.json").read_text(encoding="utf-8"))
    assert sorted(t["tracks"]["Leon"])[0][2] == "利"


# ---------------------------------------------------------------------------- an episode imported before

@ffmpeg
def test_proofread_an_existing_episode_again(tmp_path):
    root = make_workspace(tmp_path / "ws")
    d = root / "episodes" / EPISODE
    t = json.loads((d / "transcript.json").read_text(encoding="utf-8"))
    leon = sorted(t["tracks"]["Leon"])
    leon[0][2], leon[1][2] = "利", "奥"
    t["tracks"]["Leon"] = leon
    (d / "transcript.json").write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")
    fx, m = fixer(answer=find([("利奥", "Leon")]))
    c = TestClient(create_app(root, MockEditorAdapter(), web_dist=Path("/nonexistent"), transcript_fixer=fx))
    before = c.get(f"/api/episodes/{EPISODE}").json()
    r = c.post(f"/api/episodes/{EPISODE}/transcript/fix", json={"playhead": 1.0})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["fixes"] == [{"wrong": "利奥", "right": "Leon", "count": 1}] and out["changed"] == 1 and out["ai"]
    assert out["version"] == before["version"] and len(out["edits"]) == len(before["edits"])    # audio untouched
    assert out["transcript_rev"] != before["transcript_rev"]
    assert (d / "transcript.before_fix.json").is_file()
    lines = c.get(f"/api/episodes/{EPISODE}/manual/transcript", params={"t0": 0, "t1": 5}).json()["lines"]
    assert lines[0]["words"][0][0] == "Leon"
    # nothing left to fix: no change, the backup keeps the original
    again = c.post(f"/api/episodes/{EPISODE}/transcript/fix", json={}).json()
    assert again["changed"] == 0 and again["transcript_rev"] == out["transcript_rev"]
    kept = json.loads((d / "transcript.before_fix.json").read_text(encoding="utf-8"))
    assert sorted(kept["tracks"]["Leon"])[0][2] == "利"


# ---------------------------------------------------------------------------- system terms, automatic pass

def test_system_terms_apply_to_every_project_and_only_admins_change_them(tmp_path):
    from lacuna_app import system_terms
    from tests.app.e2e.auth import FakeMailer
    PW = "correct horse battery"
    root = make_workspace(tmp_path / "ws")
    leon = TestClient(create_app(root, MockEditorAdapter(), web_dist=tmp_path / "none", mailer=FakeMailer()))
    leon.post("/api/auth/register", json={"email": "leon@example.com", "password": PW})
    link = leon.post("/api/auth/invites", json={"email": "beta@example.com"}).json()["link"]
    beta = TestClient(leon.app)
    assert beta.post("/api/auth/register", json={"invite": link.rsplit("/", 1)[1], "password": PW}).status_code == 200
    # the two Leon asked for are there from the start; a creator sees them but can't change them
    assert beta.get("/api/app/terms").json() == {"terms": ["ChatGPT", "Claude Code"], "can_edit": False}
    assert beta.put("/api/app/terms", json={"terms": ["x"]}).status_code == 403
    r = leon.put("/api/app/terms", json={"terms": ["ChatGPT", " Claude  Code ", "chatgpt", "", "Sora"]})
    assert r.json() == {"terms": ["ChatGPT", "Claude Code", "Sora"], "can_edit": True}
    # beta's own project (another workspace folder) proofreads with them too
    space = next((root / "spaces").iterdir())
    assert system_terms.installation_root(space) == root
    assert {"ChatGPT", "Claude Code", "Sora"} <= set(tf.glossary_for(space).terms)


@ffmpeg
def test_an_episode_is_proofread_again_by_itself_when_the_terms_change(tmp_path):
    from lacuna_app import system_terms
    root = make_workspace(tmp_path / "ws")
    fx, m = fixer()
    c = TestClient(create_app(root, MockEditorAdapter(), web_dist=Path("/nonexistent"), transcript_fixer=fx))
    url = f"/api/episodes/{EPISODE}/transcript/fix"
    assert c.get(url).json() == {"due": True}               # imported before: due once
    c.post(url, json={})
    assert c.get(url).json() == {"due": False} and len(m.calls) == 1
    system_terms.save(root, ["ChatGPT", "Claude Code", "Sora"])
    assert c.get(url).json() == {"due": True}               # new system term: due again
    # a request that failed is asked again next time
    m.error = TimeoutError()
    c.post(url, json={})
    assert c.get(url).json() == {"due": True}
    # without the AI nothing is due (the page doesn't ask)
    off = TestClient(create_app(root, MockEditorAdapter(), web_dist=Path("/nonexistent"),
                                transcript_fixer=tf.TranscriptFixer(api_key="")))
    assert off.get(url).json() == {"due": False}


# ---------------------------------------------------------------------------- audio first (decision transcript-audio-first)

def test_sounds_alike_accepts_mishearings_and_refuses_other_names():
    for wrong, right in [("利奥", "Leon"), ("里昂", "Leon"), ("配", "Pei"), ("洛城二三世", "洛城二三事"),
                         ("pose", "PULSE"), ("拆GPT", "ChatGPT"), ("克劳德", "Claude")]:
        assert tf.sounds_alike(wrong, right), (wrong, right)
    for wrong, right in [("洛城二三事", "TEST Project"), ("Leon", "LI"), ("Pei", "WANG"), ("pose", "EPISODE"),
                         ("节目", "EPISODE"), ("Leon", "WANG")]:
        assert not tf.sounds_alike(wrong, right), (wrong, right)


def leons_test_project():
    """Leon's case (2026-10-20): project "TEST Project", hosts LI / WANG, episode "TEST EPISODE", but the
    audio is a real 洛城二三事 episode with Leon and Pei."""
    lines = [tf.Line("L0001", "LI", words("大", "家", "好")),
             tf.Line("L0002", "WANG", words("欢", "迎", "你", "来", "听", "洛", "城", "二", "三", "事", t0=2)),
             tf.Line("L0003", "LI", words("我", "是", "Leon", t0=4)),
             tf.Line("L0004", "WANG", words("我", "是", "Pei", t0=5)),
             tf.Line("L0005", "LI", words("那", "这", "期", "又", "是", "一", "期", "pose", t0=6))]
    g = tf.Glossary(terms=["TEST Project", "LI", "WANG", "TEST", "EPISODE", "Leon"], show="TEST Project", title="TEST EPISODE")
    return lines, g


def test_the_audio_wins_over_the_projects_names():
    lines, g = leons_test_project()
    forced = [{"line": "L0002", "wrong": "洛城二三事", "right": "TEST Project"},
              {"line": "L0003", "wrong": "Leon", "right": "LI"},
              {"line": "L0004", "wrong": "Pei", "right": "WANG"},
              {"line": "L0005", "wrong": "pose", "right": "EPISODE"}]
    assert tf.check(forced, lines, g) == []
    fx, m = fixer(answer=lambda _: forced)
    assert fx.fix(lines, g) == []
    assert [ln.text for ln in lines[1:4]] == ["欢迎你来听洛城二三事", "我是Leon", "我是Pei"]
    # a real mis-hearing of a term is still fixed
    mis = [tf.Line("L0001", "LI", words("我", "是", "利", "奥"))]
    assert tf.check([{"line": "L0001", "wrong": "利奥", "right": "Leon"}], mis, g) == \
        [{"line": "L0001", "wrong": "利奥", "right": "Leon"}]


def test_names_an_older_pass_forced_in_are_put_back():
    lines, g = leons_test_project()
    old = [{"line": "L0002", "wrong": "洛城二三事", "right": "TEST Project"},
           {"line": "L0003", "wrong": "Leon", "right": "LI"},
           {"line": "L0005", "wrong": "利奥", "right": "Leon"}]               # a fair one stays
    tf.apply(lines, old[:2])
    assert lines[1].text == "欢迎你来听TEST Project" and lines[2].text == "我是LI"
    assert tf.undo_forced(lines, old) == 2
    assert lines[1].text == "欢迎你来听洛城二三事" and lines[2].text == "我是Leon"
    assert lines[1].words[-1]["end"] == pytest.approx(2 + 9 * 0.3 + 0.25)          # times kept


@ffmpeg
def test_an_episode_proofread_before_gets_back_what_was_said(tmp_path):
    root = make_workspace(tmp_path / "ws")
    d = root / "episodes" / EPISODE
    t = json.loads((d / "transcript.json").read_text(encoding="utf-8"))
    (d / "transcript.before_fix.json").write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")
    leon = sorted(t["tracks"]["Leon"])
    said = leon[0][2]
    leon[0][2] = "WANG"                                    # an older pass forced a host name over the first word
    t["tracks"]["Leon"] = leon
    (d / "transcript.json").write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")
    fx, m = fixer()
    c = TestClient(create_app(root, MockEditorAdapter(), web_dist=Path("/nonexistent"), transcript_fixer=fx))
    url = f"/api/episodes/{EPISODE}/transcript/fix"
    g = tf.glossary_for(root, "", ["Leon", "Pei"])
    tf.mark_checked(d, g)
    (d / tf.CHECK_FILE).write_text(json.dumps({"sig": tf.signature(g)}), encoding="utf-8")    # checked by the old rule
    assert c.get(url).json() == {"due": True}
    out = c.post(url, json={}).json()
    assert out["changed"] == 1
    now = json.loads((d / "transcript.json").read_text(encoding="utf-8"))
    assert sorted(now["tracks"]["Leon"])[0][2] == said
    assert c.get(url).json() == {"due": False} and tf.checked_version(d) == tf.CHECK_VERSION
