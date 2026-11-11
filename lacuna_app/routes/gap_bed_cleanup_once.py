"""Leon 2026-10-30 22:28Z: the first 自动铺底 spread beds all over his episode. He asked to clean it up so he can
test 间隙 and 自动铺底 again from a clean state: keep his 片头 and 片尾, remove every other piece of music and all
gaps. Run once per workspace at startup in the cloud (marker file), only on episodes touched by those features
(a 自动铺底 bed or a gaps file; both exist only since 2026-10-30). The music file as it was is kept beside it
(music.json.before-cleanup-20261030). This module goes away in a later release."""
from __future__ import annotations

import logging
import shutil

from .. import cloud, gaps
from ..music import FILE as MUSIC
from ..store import atomic_write_json, read_json

log = logging.getLogger("lacuna.gap_bed_cleanup")
MARKER = ".gap-bed-cleanup-2026-10-30"
KEEP = ("intro", "outro")


def run(root) -> list[str]:
    out = []
    eps = root / "episodes"
    for d in sorted(eps.iterdir()) if eps.is_dir() else []:
        music, gap = d / MUSIC, d / gaps.FILE
        doc = read_json(music) if music.exists() else None
        beds = bool(doc) and any(p.get("source") == "autobed" for p in doc.get("placements", []))
        has_gaps = gap.exists() and bool(read_json(gap).get("gaps"))
        if not beds and not has_gaps:
            continue
        if doc:
            shutil.copy2(music, d / (MUSIC + ".before-cleanup-20261030"))
            doc["placements"] = [p for p in doc.get("placements", []) if p.get("role") in KEEP]
            doc["draft"] = None
            atomic_write_json(music, doc)
        if has_gaps:
            atomic_write_json(gap, {"schema": gaps.SCHEMA, "gaps": []})
        out.append(d.name)
    (root / MARKER).write_text("done\n", encoding="utf-8")
    return out


def register(app, ctx) -> None:
    if not cloud.enabled() or (ctx.ws.root / MARKER).exists():
        return
    try:
        done = run(ctx.ws.root)
    except Exception:                  # the site must start; tried again at the next start
        log.exception("gap / bed cleanup: not done")
        return
    log.warning("gap / bed cleanup done: %s", done)
