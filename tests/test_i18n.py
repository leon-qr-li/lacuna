"""Interface language on the server (lacuna_app/i18n.py): Chinese UI text goes through tr() / N_()
and has English; the language comes from the lacuna_lang cookie."""
from __future__ import annotations

import ast
import re
from pathlib import Path

from lacuna_app import i18n
from lacuna_app.i18n_en import EN

APP = Path(__file__).resolve().parents[1] / "lacuna_app"
HAN = re.compile(r"[㐀-鿿]")
# input for Claude, not UI: the episode document (show content is Chinese)
EXEMPT = {"features.py", "i18n.py", "i18n_en.py"}
REGEX_CALLS = {"compile", "search", "match", "fullmatch", "sub", "findall", "split"}


def _scan():
    bare, keys = [], []
    for p in sorted(APP.rglob("*.py")):
        if p.name in EXEMPT:
            continue
        src = p.read_text(encoding="utf-8")
        lines = src.split("\n")
        tree = ast.parse(src)
        parents = {c: n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
        docs = {n.body[0].value for n in ast.walk(tree)
                if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}

        def ignored(n):
            return any(lines[i].rstrip().endswith("# i18n-ignore") for i in range(n.lineno - 1, n.end_lineno))

        def call_name(c):
            f = c.func
            return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""

        for n in ast.walk(tree):
            if not (isinstance(n, ast.Constant) and isinstance(n.value, str) and HAN.search(n.value)):
                continue
            par = parents.get(n)
            where = f"{p.relative_to(APP.parent)}:{n.lineno}"
            if isinstance(par, ast.Call) and par.args and par.args[0] is n and call_name(par) in ("tr", "N_"):
                keys.append((where, n.value))
                continue
            if n in docs or ignored(n) or (isinstance(par, ast.Call) and call_name(par) in REGEX_CALLS) \
                    or (isinstance(par, ast.Dict) and n in par.keys):      # lookup keys (data)
                continue
            bare.append(f"{where}: {n.value[:50]!r}")
    return bare, keys


def test_ui_text_goes_through_tr_and_has_english():
    bare, keys = _scan()
    assert not bare, "Chinese outside tr() / N_() (mark content lines `# i18n-ignore`):\n" + "\n".join(bare)
    missing = sorted({f"{w}: {k!r}" for w, k in keys if k not in EN})
    assert not missing, "no English in lacuna_app/i18n_en.py for:\n" + "\n".join(missing)


def test_english_keeps_the_placeholders():
    for zh, en in EN.items():
        for e in en if isinstance(en, tuple) else (en,):
            assert set(re.findall(r"\{(\w+)\}", e)) <= set(re.findall(r"\{(\w+)\}", zh)), zh


def test_tr_follows_the_request_language_and_jobs_use_the_last_one():
    tok = i18n.set_request_lang("en")
    try:
        assert i18n.tr("找不到文件：{p}", p="a.wav") == "File not found: a.wav"
        assert i18n.tr("没有这个中文") == "没有这个中文"          # no English: Chinese
    finally:
        i18n.reset_request_lang(tok)
    assert i18n.lang() == "en"                                  # a background job after that request
    tok = i18n.set_request_lang("zh")
    i18n.reset_request_lang(tok)
    assert i18n.tr("找不到文件：{p}", p="a.wav") == "找不到文件：a.wav"
    assert i18n.set_request_lang("fr") is None and i18n.lang() == "zh"
