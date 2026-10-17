"""Create a DEMO episode in a LACUNA workspace from EP001's raw tracks.

The "first cut" here is not AI output: its cut positions are Leon's real hand edit of EP001
(S4 alignment map, `spikes/s4_alignment/out/ep001_alignment.json`) restricted to a window of
the raw recording; categories, reasons and confidence are synthesised from the map's
features and labelled as demo. The real AI first cut (S5) will replace this source.

Audio is referenced by absolute path (read-only) - nothing is copied.

    python scripts/make_demo_episode.py --workspace ~/LACUNA_Workspace
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lacuna_core import MediaRef, Project, new_timeline  # noqa: E402
from lacuna_core.edl import Clip, Track, replace  # noqa: E402
from lacuna_app.episode import Edit, create_episode  # noqa: E402
from lacuna_app.store import Workspace  # noqa: E402

ALIGNMENT = ROOT / "spikes/s4_alignment/out/ep001_alignment.json"
TOKENS = ROOT / "spikes/s5_first_cut/out/ep001_tokens.json"
RAW_DIR = Path("/mnt/user-data/uploads/Projects")
NAMES = {"Leon": "原始双轨_Leon.wav", "Pei": "原始双轨_Pei.wav"}
DEMO_TAG = "（演示：位置取自 Leon 手剪成品，理由为合成）"
CONF = {"high": 0.85, "medium": 0.65, "low": 0.45}


def overlap(a, b, c, d) -> float:
    return max(0.0, min(b, d) - max(a, c))


def minus(ranges, cut_ranges):
    """Interval difference ranges - cut_ranges (both lists of [a, b])."""
    out = []
    for a, b in ranges:
        cur = a
        for c, d in sorted(cut_ranges):
            if d <= cur or c >= b:
                continue
            if c > cur:
                out.append((cur, c))
            cur = max(cur, d)
        if cur < b:
            out.append((cur, b))
    return [(a, b) for a, b in out if b - a > 0.02]


def classify_joint(ev: dict | None, dur: float) -> tuple[str, str, str, float, bool]:
    """(category, title, reason, confidence, consequential) for a cut on both tracks."""
    frac = max((ev or {}).get("removed_speech_frac", {}).values(), default=0.0) if ev else 0.5
    conf = CONF.get((ev or {}).get("confidence"), 0.6)
    final_pause = (ev or {}).get("final_pause_at_cut_s")
    if frac < 0.1:
        keep = f"，保留约 {final_pause:.1f} 秒" if final_pause else ""
        return "pause", f"停顿收紧 · 去掉 {dur:.1f} 秒", f"两人都没说话的空白偏长{keep}。", conf, False
    if dur >= 3.0 and frac >= 0.3:
        return ("content", f"删除 {dur:.0f} 秒 · 内容删减",
                "这段偏离主线、或和前面重复，删掉后前后两句能接上。", max(conf - 0.2, 0.4), True)
    return "filler", f"口误 / 重复 · {dur:.1f} 秒", "说到一半重来或无意识的重复，去掉后语义不变。", conf, False


def build(al: dict, media: dict[str, MediaRef], w0: float, w1: float, tokens: dict | None):
    sr = next(iter(media.values())).sample_rate
    S = lambda s: int(round((s - w0) * sr))  # noqa: E731  raw seconds -> base samples
    tracks = []
    for name, ref in media.items():
        a, b = int(round(w0 * sr)), min(int(round(w1 * sr)), ref.frames)
        tracks.append(Track(name, (Clip(f"{name[0]}0", ref.media_id, a, b, 0),)))
    base = replace(new_timeline(sr, list(media)), tracks=tuple(tracks), next_id=1)
    project = Project({m.media_id: m for m in media.values()}, base)

    joint_events = [e for e in al["edit_events"] if e["kind"] == "joint" and e["type"] == "cut"]
    both = [(max(a, w0), min(b, w1)) for a, b in al["removed_raw"]["both_tracks"] if b > w0 and a < w1]
    both = [(a, b) for a, b in both if b - a > 0.02]
    edits: list[Edit] = []

    def add(ops, cat, title, reason, conf, cons):
        edits.append(Edit(f"e{len(edits) + 1:04d}", ops, cat, title, reason + DEMO_TAG, round(conf, 2), cons))

    gains = al["stats"]["median_gain"]
    for name in media:
        db = round(20 * math.log10(gains[name]), 1)
        if abs(db) >= 0.5:
            add([{"op": "track_gain", "track": name, "gain_db": db}], "loudness",
                f"{name} 音轨 {db:+.1f} dB", "两轨响度匹配。", 0.95, False)
    for a, b in both:
        ev = max(joint_events, key=lambda e: overlap(a, b, *e["raw_leon"]), default=None)
        if ev and overlap(a, b, *ev["raw_leon"]) <= 0:
            ev = None
        cat, title, reason, conf, cons = classify_joint(ev, b - a)
        add([{"op": "cut", "start": S(a), "end": S(b), "tracks": None}], cat, title, reason, conf, cons)
    # material removed on one track only (the other host kept talking) -> lift on that track
    for name in media:
        own = [(max(a, w0), min(b, w1)) for a, b in al["removed_raw"][name] if b > w0 and a < w1]
        for a, b in minus(own, both):
            d = b - a
            if d >= 4.0:
                add([{"op": "lift", "track": name, "start": S(a), "end": S(b)}], "content",
                    f"删除 {name} 单轨 {d:.0f} 秒", f"只删 {name} 这一轨的这段话，对方同时说的内容保留。",
                    0.5, True)
            elif d >= 1.0:
                add([{"op": "lift", "track": name, "start": S(a), "end": S(b)}], "interjection",
                    f"删除插话 · {name} {d:.1f} 秒", f"{name} 在对方说话时插的一句，删掉让对方说完整。",
                    0.6, True)
            else:
                add([{"op": "lift", "track": name, "start": S(a), "end": S(b)}], "single_track",
                    f"{name} 单轨删减 {d:.1f} 秒", "只动一条音轨，对方的话不受影响。", 0.7, False)
    for m in al["muted_track_spans"]:
        a, b = max(m["raw"][0], w0), min(m["raw"][1], w1)
        if b - a > 0.05 and not any(overlap(a, b, c, d) for c, d in both):
            add([{"op": "lift", "track": m["track"], "start": S(a), "end": S(b)}], "crosstalk",
                f"{m['track']} 单轨杂声 {b - a:.1f} 秒", "压在对方说话下的杂声或附和，静音这一轨。",
                0.75, False)

    transcript = None
    if tokens:
        key = {"Leon": "L", "Pei": "P"}
        transcript = {"tracks": {name: [[round(t["start"] - w0, 3), round(t["end"] - w0, 3), t["t"]]
                                        for t in tokens["tracks"][key[name]] if w0 <= t["start"] < w1]
                                 for name in media}}
    return project, edits, transcript


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--raw-dir", default=str(RAW_DIR))
    ap.add_argument("--episode", default="EP001_演示")
    ap.add_argument("--start", type=float, default=600.0, help="window start, raw seconds")
    ap.add_argument("--minutes", type=float, default=10.0)
    args = ap.parse_args(argv)

    raw_dir = Path(args.raw_dir)
    media = {}
    for name, fn in NAMES.items():
        print(f"hashing {fn} …", flush=True)
        media[name] = MediaRef.probe(raw_dir / fn)
    al = json.loads(ALIGNMENT.read_text())
    tokens = json.loads(TOKENS.read_text()) if TOKENS.is_file() else None
    w0, w1 = args.start, args.start + args.minutes * 60
    project, edits, transcript = build(al, media, w0, w1, tokens)
    meta = {"title": "EP001 样本集（10 分钟演示片段）", "demo": True,
            "demo_note": "演示数据：剪辑位置取自 Leon 的手剪成品，分类 / 理由 / 把握度为合成，之后由 AI 第一刀替换。",
            "raw_offset_s": w0, "source": "s4_alignment(ep001) demo"}
    d = create_episode(Workspace(args.workspace), args.episode, meta, project, edits, transcript)
    cons = sum(e.consequential for e in edits)
    print(f"wrote {d}: {len(edits)} edits ({cons} to review), transcript={'yes' if transcript else 'no'}")


if __name__ == "__main__":
    main()
