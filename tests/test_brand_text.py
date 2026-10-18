"""Brand rule (backlog item 28): users never see the AI vendor's name. Server interface text (tr() /
N_() keys and their English) says LACUNA, and every prompt whose output Leon reads tells the model it
is LACUNA. The web side is checked by web/scripts/brand-check.mjs (npm run build) and
web/e2e/brand_text.spec.ts (every screen, both languages)."""
from __future__ import annotations

import re

from lacuna_app import dictation_fix, editor, i18n, lessons, library, music_assist, publish
from lacuna_app.i18n_en import EN
from tests.test_i18n import _scan

VENDOR = re.compile(r"claude|anthropic|sk-ant", re.I)


def test_server_interface_text_never_names_the_vendor():
    _, keys = _scan()
    bad = [f"{w}: {k!r}" for w, k in keys if VENDOR.search(k)]
    for zh, en in EN.items():
        for e in (en if isinstance(en, tuple) else (en,)):
            if VENDOR.search(zh) or VENDOR.search(e):
                bad.append(f"i18n_en.py: {zh!r} -> {e!r}")
    assert not bad, "user-visible text must say LACUNA, not Claude / Anthropic:\n" + "\n".join(bad)


def test_prompts_whose_output_leon_reads_name_the_ai_lacuna():
    for system in (dictation_fix.SYSTEM, editor.SYSTEM, lessons.REWRITE_SYSTEM, lessons.LESSONS_SYSTEM, music_assist.SYSTEM, library.LOOKUP_SYSTEM,
                   publish.ClaudePublisher.system()):
        assert system.endswith(i18n.AI_NAME_RULE)
    assert "LACUNA" in i18n.AI_NAME_RULE


def test_error_messages_say_ai_service():
    msg = editor.error_message(TimeoutError())
    assert not VENDOR.search(msg)
