"""Create an episode in a LACUNA workspace from the AI editor's first cut (S5 edit ops).

The ops (``spikes/s5_first_cut/edit_ops.schema.json``) reference raw token ids / raw seconds;
`lacuna_app.ai_cut` maps them to reviewable edits, refining cut points on the source audio.
Audio is referenced by absolute path (read-only) - nothing is copied or written.

    python scripts/make_ai_episode.py --workspace ~/LACUNA_Workspace \\
        --ops spikes/s5_first_cut/out/ai_v3_full_ops.json
    # a window only (raw seconds):
    python scripts/make_ai_episode.py --workspace ws --ops ... --start 2200 --minutes 10
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lacuna_core import MediaRef  # noqa: E402
from lacuna_app.ai_cut import build_episode, load_tokens, report_dict  # noqa: E402
from lacuna_app.episode import create_episode  # noqa: E402
from lacuna_app.store import Workspace  # noqa: E402

TOKENS = ROOT / "spikes/s5_first_cut/out/ep001_tokens.json"
OPS = ROOT / "spikes/s5_first_cut/out/ai_v3_full_ops.json"
RAW_DIR = Path("/mnt/user-data/uploads/Projects")
NAMES = {"Leon": ("原始双轨_Leon.wav", "Leon.wav"), "Pei": ("原始双轨_Pei.wav", "Pei.wav")}


def find_raw(raw_dir: Path) -> dict[str, Path]:
    out = {}
    for name, candidates in NAMES.items():
        path = next((raw_dir / fn for fn in candidates if (raw_dir / fn).is_file()), None)
        if path is None:
            raise FileNotFoundError(f"no raw track for {name} in {raw_dir} (looked for {', '.join(candidates)})")
        out[name] = path
    return out


def build(media: dict[str, MediaRef], ops_doc: dict, tokens, w0: float, w1: float | None):
    """(project, edits, transcript, report) for raw window [w0, w1) (w1 None = to the end)."""
    return build_episode(media, ops_doc, tokens, w0, w1)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--raw-dir", default=str(RAW_DIR))
    ap.add_argument("--episode", default="EP001_AI")
    ap.add_argument("--ops", default=str(OPS), help="AI edit ops JSON")
    ap.add_argument("--tokens", default=str(TOKENS))
    ap.add_argument("--start", type=float, default=0.0, help="window start, raw seconds (default 0)")
    ap.add_argument("--minutes", type=float, default=None, help="window length (default: to the end)")
    ap.add_argument("--title", default="EP001 · AI 第一刀")
    args = ap.parse_args(argv)

    try:
        raw = find_raw(Path(args.raw_dir))
    except FileNotFoundError as e:
        sys.exit(str(e))
    media = {}
    for name, path in raw.items():
        print(f"hashing {path.name} …", flush=True)
        media[name] = MediaRef.probe(path)
    ops_doc = json.loads(Path(args.ops).read_text(encoding="utf-8"))
    tokens = load_tokens(args.tokens)
    w0 = args.start
    w1 = None if args.minutes is None else w0 + args.minutes * 60
    project, edits, transcript, report = build(media, ops_doc, tokens, w0, w1)
    meta = {"title": args.title, "demo": False, "raw_offset_s": w0,
            "source": f"ai_cut:{Path(args.ops).name}",
            "ai_model": ops_doc.get("model", "") if isinstance(ops_doc, dict) else "",
            "ai_report": report_dict(report)}
    d = create_episode(Workspace(args.workspace), args.episode, meta, project, edits, transcript)
    cons = sum(e.consequential for e in edits)
    print(f"wrote {d}: {len(edits)} edits ({cons} to review)")
    print(report.summary())
    for w in report.warnings[:20]:
        print("  " + w)
    if len(report.warnings) > 20:
        print(f"  … {len(report.warnings) - 20} more")


if __name__ == "__main__":
    main()
