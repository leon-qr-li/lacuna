"""Blind comparison of two models for the AI producer chat (decision 2026-10-25-ai-cost-cut): the chat stays on
Opus until Sonnet gives answers as good on the same requests. Replays the host's own past requests (chat.json)
on both models, without changing anything, and writes a page where each answer pair is shown as A / B in random
order, plus the key and the cost of each model.

    python scripts/chat_blind_compare.py --workspace C:\\Projects\\LACUNA_Workspace --episode EP001_AI \\
        --episode EP002 --turns 20 --out C:\\Projects\\chat_blind

Writes <out>/blind.html (judge it without the key), <out>/key.json (which side was which) and
<out>/results.json (every answer, tokens, seconds, cost). The scene is built on the episode's current cut, so a
request whose edit was later approved may now point at audio already removed; skip those when judging.
Needs an API key (find_api_key); costs roughly $0.02 per request per model.
"""
from __future__ import annotations

import argparse
import html
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lacuna_app import Episode, Workspace  # noqa: E402
from lacuna_app.editor import ClaudeEditorAdapter, find_api_key  # noqa: E402

MODELS = ("claude-opus-5-5", "claude-sonnet-5-5")


def history_before(log: list[dict], i: int, keep: int = Episode.CHAT_HISTORY) -> list[dict]:
    """The earlier turns as the editor saw them when turn `i` was asked (Episode.chat_history at that moment)."""
    out = []
    for turn in log[max(0, i - keep):i]:
        outcome = "no change proposed"
        if turn.get("proposal"):
            outcome = {"pending": "proposed, not decided yet", "approved": "proposed and approved",
                       "discarded": "proposed and rejected"}.get(turn.get("state", "pending"), "proposed")
        out.append({"said": turn["said"], "at": turn["at"], "you_replied": turn["reply"], "outcome": outcome})
    return out


def answer(adapter: ClaudeEditorAdapter, ctx) -> dict:
    p = adapter.propose(ctx)
    cuts, restores = p.normalized()
    return {"message": p.message, "notes": list(p.notes), "usage": p.usage,
            "cuts": [{"start": round(c["start"], 2), "end": round(c["end"], 2), "track": c.get("track")} for c in cuts],
            "restores": list(restores)}


def describe(a: dict) -> str:
    lines = [a["message"]]
    lines += [f"✂ {c['start']:.2f}–{c['end']:.2f} s ({c['end'] - c['start']:.2f} s, {c['track'] or 'both tracks'})"
              for c in a["cuts"]]
    lines += [f"↺ restore {r}" for r in a["restores"]]
    lines += [f"note: {n}" for n in a["notes"]]
    return "\n".join(lines)


def page(rows: list[dict]) -> str:
    cards = []
    for n, r in enumerate(rows, 1):
        cards.append(f"""<section><h2>{n}. {html.escape(r['episode'])} @ {html.escape(r['at'])}</h2>
<p class="said">“{html.escape(r['said'])}”</p>
<div class="pair"><div><h3>A</h3><pre>{html.escape(describe(r['A']))}</pre></div>
<div><h3>B</h3><pre>{html.escape(describe(r['B']))}</pre></div></div>
<p class="pick">A 更好 ☐ · 一样 ☐ · B 更好 ☐</p></section>""")
    return f"""<!doctype html><meta charset="utf-8"><title>Chat blind comparison</title>
<style>body{{font:15px/1.5 system-ui,sans-serif;max-width:980px;margin:24px auto;padding:0 16px}}
.pair{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}pre{{white-space:pre-wrap;background:#f4f4f6;
padding:10px;border-radius:8px}}.said{{font-size:17px}}section{{border-bottom:1px solid #ddd;padding:8px 0 16px}}</style>
<h1>对话修改盲比（{len(rows)} 条）</h1><p>每条的 A / B 顺序随机；看完再打开 key.json。</p>{''.join(cards)}"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--episode", action="append", required=True)
    ap.add_argument("--turns", type=int, default=20, help="latest requests per episode")
    ap.add_argument("--models", default=",".join(MODELS))
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    key, where = find_api_key()
    if not key:
        print("api key: MISSING")
        return 2
    print(f"api key: found ({where})")
    first, second = a.models.split(",")
    adapters = {m: ClaudeEditorAdapter(api_key=key, model=m) for m in (first, second)}
    rng = random.Random(a.seed)
    ws = Workspace(a.workspace)
    rows, key_out, results = [], [], []
    for eid in a.episode:
        ep = Episode(ws, eid)
        log = ep.chat_log()
        for i in range(max(0, len(log) - a.turns), len(log)):
            turn = log[i]
            ctx, _ = ep.chat_context(turn["said"], float(turn["at"]))
            ctx.history = history_before(log, i)
            got = {m: answer(ad, ctx) for m, ad in adapters.items()}
            flip = rng.random() < 0.5
            sides = (second, first) if flip else (first, second)
            at = f"{int(turn['at'] // 60)}:{turn['at'] % 60:05.2f}"
            rows.append({"episode": eid, "at": at, "said": turn["said"], "A": got[sides[0]], "B": got[sides[1]]})
            key_out.append({"n": len(rows), "A": sides[0], "B": sides[1]})
            results.append({"episode": eid, "at": turn["at"], "said": turn["said"], "answers": got})
            print(f"{len(rows):3d}. {eid} @ {at} {turn['said']!r} done")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "blind.html").write_text(page(rows), encoding="utf-8")
    (out / "key.json").write_text(json.dumps(key_out, ensure_ascii=False, indent=1), encoding="utf-8")
    totals = {m: {"cost_usd": round(sum((r["answers"][m]["usage"] or {}).get("cost_usd", 0) for r in results), 4),
                  "seconds": round(sum((r["answers"][m]["usage"] or {}).get("seconds", 0) for r in results), 1)}
              for m in adapters}
    (out / "results.json").write_text(json.dumps({"totals": totals, "turns": results}, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    print(json.dumps(totals))
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
