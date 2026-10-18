"""Interface language for text the server shows (errors, job stages, labels, AI meta-text).

The web app keeps the choice (中文 / English) in the ``lacuna_lang`` cookie; the middleware in
``routes/i18n.py`` sets it for each request. Background jobs (import, export, publish, poster)
run outside a request and use the language of the last request, which for a one-person local
app is the language on screen.

Like the web side (``web/src/i18n``), the Chinese text is the key: ``tr("找不到文件：{name}", name=p)``.
English lives in ``i18n_en.py``. ``N_("…")`` marks a Chinese label kept in a table and translated
where it is used (``tr(LABELS[k])``). ``tests/test_i18n.py`` fails on Chinese outside these
calls and on keys without English; a line ending in ``# i18n-ignore`` is content, not UI (the
show is Chinese: transcripts, show notes, prompts to Claude).
"""
from __future__ import annotations

import contextvars
import json
import re

COOKIE = "lacuna_lang"
_current: contextvars.ContextVar[str | None] = contextvars.ContextVar("lacuna_lang", default=None)
_last: str = "zh"


def normalize(value: str | None) -> str | None:
    return value if value in ("zh", "en") else None


def lang() -> str:
    return _current.get() or _last


def set_request_lang(value: str | None) -> contextvars.Token | None:
    """Called per request: the cookie's language (if any) for this request and later jobs."""
    global _last
    v = normalize(value)
    if v is None:
        return None
    _last = v
    return _current.set(v)


def reset_request_lang(token: contextvars.Token | None) -> None:
    if token is not None:
        _current.reset(token)


def _fill(s: str, kw: dict) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: str(kw[m.group(1)]) if m.group(1) in kw else m.group(0), s) if kw else s


def tr(zh: str, /, **kw) -> str:
    """The interface-language version of ``zh`` with ``{name}`` filled from ``kw``."""
    if lang() == "en":
        from .i18n_en import EN
        e = EN.get(zh)
        if isinstance(e, tuple):  # (singular, plural), picked by n
            e = e[0] if kw.get("n") == 1 else e[1]
        if e is not None:
            return _fill(e, kw)
    return _fill(zh, kw)


def N_(zh: str) -> str:
    """Marks a label for translation where it is used (``tr(label)``); returns it unchanged."""
    return zh


def join_list(items) -> str:
    return (", " if lang() == "en" else "、").join(items)


# appended to every system prompt whose output Leon reads: the AI is "LACUNA" to users (brand rule,
# backlog item 28); the vendor's name never shows up in the app
AI_NAME_RULE = ("\n\nIf you ever refer to yourself, you are LACUNA, the AI inside LACUNA Studio. Never call "
                "yourself Claude and never mention Anthropic.")


def in_reply_language(obj):
    """A prompt or tool schema whose "Simplified Chinese" means "what Leon reads" (chat replies, edit
    reasons, notes), switched to English when that is the interface language. Not for show content."""
    if lang() != "en":
        return obj
    if isinstance(obj, str):
        return obj.replace("Simplified Chinese", "English")
    return json.loads(json.dumps(obj, ensure_ascii=False).replace("Simplified Chinese", "English"))
