"""Quality check of the cheaper models (decision 2026-10-25-ai-cost-cut; Leon 2026-10-25: 「质量优先」). Runs the same
real inputs through the old and the new model, without changing anything, and writes one blind page:

* chat (AI producer): the host's past requests, Opus vs Sonnet (scripts/chat_blind_compare.py);
* lessons: the episode's lesson summary and the 「记住」 rewrites, Sonnet (before) vs Haiku (now);
* credits: track-credit lookups for library items with a note, Opus (before) vs Haiku (now).

    python scripts/ai_quality_compare.py --workspace C:\\Projects\\LACUNA_Workspace --episode EP001_AI \\
        --turns 20 --credits 6 --out C:\\Projects\\ai_quality

Writes <out>/compare.html (A / B in random order per item), <out>/key.json and <out>/results.json (answers,
tokens, cost). Needs the API key (find_api_key). Nothing in the workspace is written.
"""
from __future__ import annotations

import argparse
import html
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lacuna_app import Episode, Workspace, show  # noqa: E402
from lacuna_app.chat_learning import ChatAsks  # noqa: E402
from lacuna_app.editor import ClaudeEditorAdapter, find_api_key  # noqa: E402
from lacuna_app.learning import Learning  # noqa: E402
from lacuna_app.lessons import ClaudeRuleWriter, Lessons  # noqa: E402
from lacuna_app.library import Library, lookup_request  # noqa: E402
from scripts.chat_blind_compare import answer as chat_answer, describe as chat_describe, history_before  # noqa: E402

OPUS, SONNET, HAIKU = "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"


class _Captured(Exception):
    pass


def lesson_payloads(ws: Workspace, eid: str) -> tuple[dict | None, list[dict]]:
    """(the summary payload, the 「记住」 rewrite payloads) exactly as the app builds them, writing nothing."""
    seen: dict = {}

    class Catch:
        available = True

        def summarize(self, payload, profile=None):
            seen["summary"] = payload
            raise _Captured()

    les = Lessons(ws, Learning(ws), ChatAsks(ws), Catch())
    les._set_summary = lambda *a, **k: None          # noqa: SLF001 - read-only run
    les._save = lambda *a, **k: None                 # noqa: SLF001
    ep = Episode(ws, eid)
    les.summarize(ep)
    log = ep.chat_log()
    rules = les._ask_rules()                         # noqa: SLF001
    rewrites = []
    for i, t in enumerate(log):
        if t.get("remember"):
            said = t["said"].split("：", 1)[-1]
            recent = [{"leon_said": x["said"], "producer_replied": x.get("reply", "")[:200]} for x in log[max(0, i - 6):i]]
            rewrites.append({"said": said, "recent_chat": recent, "existing_rules": rules})
    return seen.get("summary"), rewrites


def run_writer(model: str, key: str, kind: str, payload: dict, profile) -> dict:
    w = ClaudeRuleWriter(api_key=key)
    w.model = model
    t0 = time.monotonic()
    try:
        out, usage = w.summarize(payload, profile) if kind == "summary" else w.rewrite(payload, profile)
    except Exception as e:      # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}", "usage": None, "seconds": round(time.monotonic() - t0, 1)}
    return {"out": out, "usage": usage}


def run_credit(model: str, key: str, asset: dict, profile) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=key, timeout=180.0, max_retries=1)
    req = lookup_request(asset, profile)
    req["model"] = model
    extra = {}
    if model != HAIKU:          # what the lookup used before: Opus with the newer web search + fallback
        req["tools"] = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 5}] + req["tools"][1:]
        extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    messages = list(req.pop("messages"))
    t0 = time.monotonic()
    try:
        resp = None
        for _ in range(4):
            resp = client.beta.messages.create(messages=messages, **extra, **req)
            if resp.stop_reason != "pause_turn":
                break
            messages = messages + [{"role": "assistant", "content": resp.content}]
    except Exception as e:      # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}", "usage": None}
    found = next((dict(b.input) for b in resp.content if b.type == "tool_use" and b.name == "submit_credit"), None)
    text = "".join(getattr(b, "text", "") for b in resp.content if b.type == "text").strip()
    return {"out": found or {"no_credit": text}, "usage": ClaudeEditorAdapter._usage(resp, time.monotonic() - t0)}


def show_out(a: dict, kind: str) -> str:
    if kind == "chat":
        return chat_describe(a)
    if a.get("error"):
        return "ERROR " + a["error"]
    o = a["out"]
    if kind == "summary":
        return "\n\n".join(f"• {x.get('title')}\n  {x.get('instruction')}\n  ({x.get('why', '')})" for x in o) or "(none)"
    return json.dumps(o, ensure_ascii=False, indent=1)


def page(items: list[dict]) -> str:
    names = {"chat": "对话改剪辑", "summary": "学习总结", "rewrite": "「记住」改写成规则", "credit": "查曲名"}
    out = []
    for n, it in enumerate(items, 1):
        out.append(f"""<section><h2>{n}. {names[it['kind']]} · {html.escape(it['title'])}</h2>
<pre class="in">{html.escape(it['input'])}</pre>
<div class="pair"><div><h3>A</h3><pre>{html.escape(show_out(it['A'], it['kind']))}</pre></div>
<div><h3>B</h3><pre>{html.escape(show_out(it['B'], it['kind']))}</pre></div></div>
<p>A 更好 ☐ · 一样 ☐ · B 更好 ☐</p></section>""")
    return f"""<!doctype html><meta charset="utf-8"><title>AI quality comparison</title>
<style>body{{font:15px/1.5 system-ui,sans-serif;max-width:1040px;margin:24px auto;padding:0 16px}}
.pair{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}pre{{white-space:pre-wrap;background:#f4f4f6;padding:10px;
border-radius:8px}}pre.in{{background:#fff8e6}}section{{border-bottom:1px solid #ddd;padding:8px 0 16px}}</style>
<h1>模型质量盲比（{len(items)} 项）</h1><p>每项 A / B 顺序随机；看完再打开 key.json。</p>{''.join(out)}"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--episode", action="append", required=True)
    ap.add_argument("--turns", type=int, default=20)
    ap.add_argument("--credits", type=int, default=6)
    ap.add_argument("--rewrites", type=int, default=8)
    ap.add_argument("--only", default="chat,lessons,credits")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=11)
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    key, where = find_api_key()
    if not key:
        print("api key: MISSING")
        return 2
    print(f"api key: found ({where})")
    only = set(a.only.split(","))
    rng = random.Random(a.seed)
    ws = Workspace(a.workspace)
    profile = show.load(ws.root)
    items: list[dict] = []

    def add(kind, title, inp, old, new, old_m, new_m):
        flip = rng.random() < 0.5
        items.append({"kind": kind, "title": title, "input": inp, "A": new if flip else old, "B": old if flip else new,
                      "key": {"A": new_m if flip else old_m, "B": old_m if flip else new_m}})
        print(f"{len(items):3d}. {kind} {title} done")

    for eid in a.episode:
        ep = Episode(ws, eid)
        if "chat" in only:
            ads = {m: ClaudeEditorAdapter(api_key=key, model=m) for m in (OPUS, SONNET)}
            log = ep.chat_log()
            asks = [i for i, t in enumerate(log) if not t.get("remember")][-a.turns:]
            for i in asks:
                t = log[i]
                ctx, _ = ep.chat_context(t["said"], float(t["at"]))
                ctx.history = history_before(log, i)
                got = {m: chat_answer(ad, ctx) for m, ad in ads.items()}
                add("chat", f"{eid} @ {int(t['at'] // 60)}:{t['at'] % 60:04.1f}", t["said"], got[OPUS], got[SONNET],
                    OPUS, SONNET)
        if "lessons" in only:
            summary, rewrites = lesson_payloads(ws, eid)
            if summary:
                add("summary", eid, f"{len(summary['chat'])} chat turns, {len(summary['review'])} review decisions",
                    run_writer(SONNET, key, "summary", summary, profile),
                    run_writer(HAIKU, key, "summary", summary, profile), SONNET, HAIKU)
            for p in rewrites[-a.rewrites:]:
                add("rewrite", eid, p["said"], run_writer(SONNET, key, "rewrite", p, profile),
                    run_writer(HAIKU, key, "rewrite", p, profile), SONNET, HAIKU)
    if "credits" in only:
        assets = [x for x in Library(ws).assets() if (x.get("note") or "").strip()][: a.credits]
        for x in assets:
            add("credit", x.get("name", ""), f"{x.get('name')} · {x.get('note')}", run_credit(OPUS, key, x, profile),
                run_credit(HAIKU, key, x, profile), OPUS, HAIKU)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "compare.html").write_text(page(items), encoding="utf-8")
    (out / "key.json").write_text(json.dumps([{"n": n, "kind": it["kind"], **it["key"]} for n, it in enumerate(items, 1)],
                                             ensure_ascii=False, indent=1), encoding="utf-8")
    cost: dict = {}
    for it in items:
        for side in ("A", "B"):
            m = it["key"][side]
            u = it[side].get("usage") or {}
            c = cost.setdefault(f"{it['kind']}:{m}", {"cost_usd": 0.0, "seconds": 0.0, "n": 0})
            c["cost_usd"] = round(c["cost_usd"] + (u.get("cost_usd") or 0), 4)
            c["seconds"] = round(c["seconds"] + (u.get("seconds") or 0), 1)
            c["n"] += 1
    (out / "results.json").write_text(json.dumps({"cost": cost, "items": items}, ensure_ascii=False, indent=1, default=str),
                                      encoding="utf-8")
    print(json.dumps(cost, ensure_ascii=False))
    return 0 if items else 1


if __name__ == "__main__":
    raise SystemExit(main())
