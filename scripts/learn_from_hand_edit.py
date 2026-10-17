"""Learn from Leon's own edit of an episode (D29): label the AI first cut against his finished episode.

Reads the episode (read-only) and the S4 alignment of his hand edit, writes the labels as a decision
snapshot to ``<workspace>/learning/decisions/<episode>.hand_edit.json``. The learning page then shows
the candidate rules they support next to what his review taught; nothing applies until he approves.

    python scripts/learn_from_hand_edit.py --workspace C:\\Projects\\LACUNA_Workspace --episode EP001_AI
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lacuna_app.episode import Episode  # noqa: E402
from lacuna_app.learning import Learning, hand_edit_decisions, learn  # noqa: E402
from lacuna_app.store import Workspace  # noqa: E402

ALIGNMENT = ROOT / "spikes/s4_alignment/out/ep001_alignment.json"


def ground_truth(path: Path) -> tuple[dict, dict]:
    """(removed, ambiguous) raw-second spans per track from an S4 alignment (same reading as S5 score.py)."""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    removed = {t: [tuple(s) for s in d["removed_raw"][t]] for t in ("Leon", "Pei")}
    ambiguous: dict[str, list] = {"Leon": [], "Pei": []}
    for m in d["muted_track_spans"]:
        (removed if m["same_offset_heard_both_sides"] else ambiguous)[m["track"]].append(tuple(m["raw"]))
    return {t: sorted(s) for t, s in removed.items()}, ambiguous


def run(ws: Workspace, episode_id: str, alignment: Path, write: bool = True) -> list:
    removed, ambiguous = ground_truth(alignment)
    ep = Episode(ws, episode_id)
    try:
        ds = hand_edit_decisions(ep, removed, ambiguous)
    finally:
        ep.close()
    if write:
        Learning(ws).save_decisions(f"{episode_id}.hand_edit", ds)
    return ds


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--episode", default="EP001_AI")
    ap.add_argument("--alignment", default=str(ALIGNMENT))
    ap.add_argument("--dry-run", action="store_true", help="print, write nothing")
    args = ap.parse_args(argv)
    ds = run(Workspace(args.workspace), args.episode, Path(args.alignment), write=not args.dry_run)
    print(f"{len(ds)} labelled:", dict(Counter(d.verdict for d in ds)))
    for r in learn(ds):
        print(f"- [{r.kind}] {r.title}\n    {r.detail}")


if __name__ == "__main__":
    main()
