"""Clear the workspace down to one episode for a fresh test run (Leon 2026-10-18).

Keeps one episode (found by its title) and the library assets its music uses; those move from 公共 to
that episode only. Every other episode is archived and deleted for good the app's own way
(``Archive.delete``: learning evidence snapshotted first, chat kept under learning/chats/, its files
removed); every other asset is taken out of the library the app's own way (file moved to
``library/_removed/``, never erased). Learned rules (``learning/``) are never touched.

Run with the app stopped (it refuses while something answers on the port). Dry run by default;
``--apply`` does it, after copying library.json / archive.json / learning/rules.json to a backup folder.

    python scripts/keep_only_episode.py --workspace C:\\Projects\\LACUNA_Workspace --keep 生化危机
    python scripts/keep_only_episode.py --workspace C:\\Projects\\LACUNA_Workspace --keep 生化危机 --apply
"""
from __future__ import annotations

import argparse
import json
import shutil
import socket
import sys
import time
from pathlib import Path

try:
    import lacuna_app  # noqa: F401  (the installed app's own code, when run with its Python)
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lacuna_app.archive import Archive  # noqa: E402
from lacuna_app.episode import Episode  # noqa: E402
from lacuna_app.learning import Learning  # noqa: E402
from lacuna_app.library import Library  # noqa: E402
from lacuna_app.store import Workspace, read_json  # noqa: E402


def title_of(ws: Workspace, eid: str) -> str:
    try:
        return str(read_json(ws.episode_dir(eid) / "episode.json").get("title") or eid)
    except (OSError, ValueError):
        return eid


def music_assets(ws: Workspace, eid: str) -> set[str]:
    try:
        doc = read_json(ws.episode_dir(eid) / "music.json")
    except (OSError, ValueError):
        return set()
    ps = list(doc.get("placements") or []) + list((doc.get("draft") or {}).get("placements") or [])
    return {p["asset_id"] for p in ps if isinstance(p, dict) and p.get("asset_id")}


def app_running(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def plan(ws: Workspace, keep: str) -> dict:
    ids = ws.episode_ids()
    match = [e for e in ids if keep in title_of(ws, e) or keep == e]
    if len(match) != 1:
        raise SystemExit(f"--keep {keep!r} matches {len(match)} episodes: "
                         f"{[(e, title_of(ws, e)) for e in ids]}")
    kept = match[0]
    lib = Library(ws)
    doc = lib.load()
    used = music_assets(ws, kept)
    in_series = {(s.get(k) or {}).get("asset_id") for s in doc["series"] for k in ("intro", "outro")}
    return {
        "keep": {"id": kept, "title": title_of(ws, kept)},
        "delete_episodes": [{"id": e, "title": title_of(ws, e)} for e in ids if e != kept],
        "move_assets": [{"id": a["id"], "name": a["name"]} for a in doc["assets"] if a["id"] in used],
        "remove_assets": [{"id": a["id"], "name": a["name"], "in_series": a["id"] in in_series}
                          for a in doc["assets"] if a["id"] not in used],
        "series": [{"name": s.get("name"), "intro": (s.get("intro") or {}).get("asset_id"),
                    "outro": (s.get("outro") or {}).get("asset_id")} for s in doc["series"]],
    }


def backup(ws: Workspace) -> Path:
    dst = ws.root / "_backup" / f"keep_only_{time.strftime('%Y%m%d-%H%M%S')}"
    dst.mkdir(parents=True)
    for rel in ("library/library.json", "archive.json", "learning/rules.json"):
        src = ws.root / rel
        if src.is_file():
            (dst / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst / rel)
    return dst


def apply(ws: Workspace, p: dict) -> dict:
    lib, archive, learning = Library(ws), Archive(ws), Learning(ws)
    kept = p["keep"]["id"]
    for a in p["move_assets"]:
        lib.move_to(a["id"], kept)
    for a in p["remove_assets"]:
        lib.remove(a["id"])
    deleted = []
    for e in p["delete_episodes"]:
        archive.archive(e["id"])
        out = archive.delete(e["id"], keep_learning=lambda i: learning.overview([Episode(ws, i)]),
                             drop_media=lib.drop_episode)
        deleted.append(out["deleted"])
    return {"deleted": deleted, "episodes_left": ws.episode_ids(),
            "assets_left": [(a["name"], a["shared"], a["episodes"]) for a in lib.assets()]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--workspace", required=True, type=Path)
    ap.add_argument("--keep", required=True, help="the episode to keep: part of its title, or its id")
    ap.add_argument("--apply", action="store_true", help="do it (default: only print the plan)")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args(argv)
    ws = Workspace(a.workspace)
    p = plan(ws, a.keep)
    print(json.dumps(p, ensure_ascii=False, indent=2))
    if not a.apply:
        return 0
    if app_running(a.port):
        print(f"The app is running on port {a.port}: close it first.", file=sys.stderr)
        return 2
    print("backup:", backup(ws))
    print(json.dumps(apply(ws, p), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
