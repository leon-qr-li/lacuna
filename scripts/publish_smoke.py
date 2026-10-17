"""Write the publish pack of one episode with the real Claude and print it (phase 9 check).

    python scripts/publish_smoke.py --workspace C:\\Projects\\LACUNA_Workspace --episode EP001_AI

Same as the app's 「生成发布资料」 button: saves <episode>/publish.json and
<workspace>/exports/<episode>/publish/notes.md (an earlier pack of that episode is replaced).
Prints where the API key was found (never the key), the Markdown, and tokens / seconds / cost.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lacuna_app import Episode, Workspace  # noqa: E402
from lacuna_app.editor import find_api_key  # noqa: E402
from lacuna_app.publish import Publisher, make_publisher, segments  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--episode", required=True)
    ap.add_argument("--writer", choices=["auto", "claude", "rules"], default="claude")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ws = Workspace(args.workspace)
    ep = Episode(ws, args.episode)
    print(f"key: {find_api_key()[1]}; segments on the current cut: {len(segments(ep))}")
    pub = Publisher(ws, lambda: make_publisher(args.writer))
    usage: list[dict] = []
    pub.on_usage = lambda eid, u: usage.append(u)
    job = pub.start(ep, wait=True)
    if job["state"] != "done":
        print("failed:", job["error"])
        return 1
    v = pub.view(ep)
    print(v["pack"]["markdown"])
    print("names to check:", json.dumps(v["pack"]["names"], ensure_ascii=False))
    print("notes:", v["pack"]["notes"], "| saved:", v["notes_path"])
    print("usage:", json.dumps(usage, ensure_ascii=False))
    ep.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
