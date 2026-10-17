"""Ask the real Claude producer one question about an episode, without changing anything.

    python scripts/ai_chat_smoke.py --workspace C:\\Projects\\LACUNA_Workspace --episode EP001_AI \\
        --at 12:30 --say "这里停顿短一点"

Prints where the API key was found (never the key), the reply, the change it would propose
(as timeline ranges) and the tokens / seconds / estimated cost of the call.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lacuna_app import Episode, Workspace  # noqa: E402
from lacuna_app.editor import ClaudeEditorAdapter, find_api_key, scene, sdk_installed  # noqa: E402


def seconds(s: str) -> float:
    parts = [float(x) for x in s.split(":")]
    return sum(x * 60 ** i for i, x in enumerate(reversed(parts)))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--episode", required=True)
    ap.add_argument("--at", default="1:00", help="playhead m:ss on the current cut")
    ap.add_argument("--say", default="这里停顿短一点")
    ap.add_argument("--show-scene", action="store_true", help="print what is sent to Claude")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    key, where = find_api_key()
    print(f"api key: {'found (' + where + ')' if key else 'MISSING'} · anthropic sdk: {sdk_installed()}")
    if not key:
        return 2
    ep = Episode(Workspace(a.workspace), a.episode)
    ctx, _ = ep.chat_context(a.say, seconds(a.at))
    if a.show_scene:
        print(json.dumps(scene(ctx), ensure_ascii=False, indent=1))
    print(f"@ {a.at}  {a.say!r}  ({len(ctx.utterances)} utterances, {len(ctx.pauses)} pauses sent)")
    p = ClaudeEditorAdapter().propose(ctx)
    print("reply:", p.message)
    for n in p.notes:
        print("note:", n)
    cuts, restores = p.normalized()
    for c in cuts:
        print(f"cut {c['start']:.2f}–{c['end']:.2f} s ({c['end'] - c['start']:.2f} s) track={c['track'] or 'both'}")
    for r in restores:
        print("restore", r)
    print("usage:", json.dumps(p.usage, ensure_ascii=False))
    return 0 if p.usage else 1


if __name__ == "__main__":
    raise SystemExit(main())
