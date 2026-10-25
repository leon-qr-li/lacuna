"""AI prompts follow the workspace's show: Leon's show keeps its prompts word for word, any other show
gets its own name, hosts and strictness and never Leon's, Pei's or 《洛城二三事》's."""
import json
import re

import pytest

from lacuna_app import editor, first_cut, library, lessons, poster, publish, show
from lacuna_app.store import Workspace

OTHER = show.normalise({"show_name": "Ana Talks", "about": "a book podcast", "hosts": [
    {"name": "Ana", "cut_level": "firm", "style": "Cut her long lists."},
    {"name": "Bo", "cut_level": "gentle"},
    {"name": "Cy"}]}, strict=True)
SOLO = show.normalise({"show_name": "Solo Hour", "hosts": [{"name": "Dee"}]}, strict=True)
LEON = re.compile(r"\b(Leon|Pei)\b|洛城")
HE = re.compile(r"\b(he|him|his|He|His)\b")


def prompts(profile):
    """Every system prompt / instruction the AI gets, for one show."""
    poster_text = poster.ClaudeDesigner.system(profile)[0]["text"]
    pub = publish.ClaudePublisher.system(profile)
    return {
        "chat": editor.system_for(profile),
        "rewrite": lessons._for_show(lessons.REWRITE_SYSTEM, profile),
        "lessons": lessons._for_show(lessons.LESSONS_SYSTEM, profile),
        "first_cut": first_cut.system_prompt("- keep laughs", profile),
        "first_cut_tool": json.dumps(first_cut.tool_for([h["tag"] for h in profile["hosts"]], show.is_legacy(profile))),
        "show_notes": pub[:pub.index("APPROVED EXAMPLE")],           # the example itself is Leon's EP001
        "poster": poster_text[:poster_text.index("EXAMPLE —")],
        "lookup": json.dumps(library.lookup_request({"name": "a.mp3", "note": "片尾曲"}, profile), ensure_ascii=False),
    }


def test_leons_show_keeps_every_prompt_word_for_word():
    for profile in (None, show.LEGACY):
        assert editor.system_for(profile) == editor.SYSTEM
        assert lessons._for_show(lessons.REWRITE_SYSTEM, profile) == lessons.REWRITE_SYSTEM
        assert lessons._for_show(lessons.LESSONS_SYSTEM, profile) == lessons.LESSONS_SYSTEM
        assert first_cut.system_prompt("- x", profile) == first_cut.system_prompt("- x")
        assert "R2. HOST ASYMMETRY" in first_cut.system_prompt("", profile)       # Leon's EP001 calibration
        assert publish.ClaudePublisher.system(profile) == publish.ClaudePublisher.system()
        assert poster.ClaudeDesigner.system(profile) == poster.ClaudeDesigner.system()
        assert library.lookup_request({"name": "a"}, profile)["system"] == library.LOOKUP_SYSTEM


@pytest.mark.parametrize("profile", [OTHER, SOLO], ids=["three hosts", "solo"])
def test_another_show_gets_its_own_names_and_never_leons(profile):
    for name, text in prompts(profile).items():
        assert not LEON.findall(text), (name, LEON.findall(text))
        assert "<<" not in text, name
        assert profile["show_name"] in text or name == "first_cut_tool", name
    for name in ("chat", "first_cut"):
        for h in profile["hosts"]:
            assert h["name"] in prompts(profile)[name], (name, h["name"])


def test_another_show_speaks_of_the_editor_neutrally():
    for name in ("rewrite", "lessons"):
        assert not HE.findall(prompts(OTHER)[name]), name


def test_strictness_and_style_per_host_reach_the_chat_and_the_first_cut():
    for text in (editor.system_for(OTHER), first_cut.system_prompt("", OTHER)):
        assert "- Ana (track A): be strict" in text and "Cut her long lists." in text
        assert "- Bo (track B): be gentle" in text
        assert "- Cy (track C): cut clear stumbles" in text


def test_a_new_show_starts_from_defaults_not_leons_calibration():
    s = first_cut.system_prompt("- 保留笑声", OTHER)
    assert "DEFAULT EDITING RULES" in s and "R2. HOST ASYMMETRY" not in s
    assert s.endswith("- 保留笑声") and "RULES LEARNED FROM THE EDITOR'S REVIEWS" in s
    assert '"A000812" / "B000812"' in s and "track A, B, C or both" in s


def test_the_window_request_and_poster_revision_name_the_editor():
    assert "Leon" not in first_cut.window_request(0, 600, 0, 3, "The editor")
    d = poster.ClaudeDesigner(client=object())
    d.show = OTHER
    asked = []
    d._ask = lambda user: asked.append(user)
    d.revise("ctx", "<svg/>", "换成暖色")
    assert "The editor likes this cover" in asked[0] and "they ask" in asked[0] and "Leon" not in asked[0]
    d.show = None
    d.revise("ctx", "<svg/>", "换成暖色")
    assert "Leon likes this cover" in asked[1]


def test_poster_brief_names_the_workspace_show(tmp_path):
    pack = {"draft": {"title": "t", "films": [], "sections": []}}
    assert "《洛城二三事》" in poster.brief_context("EP002", pack)
    assert poster.brief_context("EP002", pack, "Ana Talks").startswith("节目：《Ana Talks》")


def test_chat_context_carries_the_workspace_show(tmp_path):
    (tmp_path / "spaces" / "sp_test").mkdir(parents=True)
    ws = Workspace(tmp_path / "spaces" / "sp_test")       # a workspace made after Leon's
    show.write_new(ws.root)
    show.save(ws.root, {"show_name": "Ana Talks", "hosts": [{"name": "Ana"}, {"name": "Bo"}]})
    ctx = editor.ChatContext("剪掉这句", 1.0, 10.0, [], None, show=show.load(ws.root))
    req = editor.ClaudeEditorAdapter(client=object()).build_request(ctx)
    assert "《Ana Talks》" in req["system"][0]["text"] and "Leon" not in req["system"][0]["text"]
    req = editor.ClaudeEditorAdapter(client=object()).build_request(editor.ChatContext("x", 1.0, 10.0, [], None))
    assert req["system"][0]["text"].startswith(editor.SYSTEM[:60])
