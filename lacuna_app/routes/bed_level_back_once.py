"""Leon 2026-10-31: the 铺底 default goes back from 25 to 22 dB under full level ("声儿有点太小了"). Beds placed
while the default was 25 dB (2026-10-30 22:13Z to now) stored bg_db 25; they go back to 22 too. Run once per
workspace at startup in the cloud (marker file); a bed set to another level by hand is left alone. This module goes
away in a later release."""
from __future__ import annotations

import logging

from .. import cloud
from ..music import BED_BG_DB, FILE as MUSIC
from ..store import atomic_write_json, read_json

log = logging.getLogger("lacuna.bed_level_back")
MARKER = ".bed-level-back-2026-10-31"
OLD = 25.0


def _fix(ps: list[dict]) -> int:
    n = 0
    for p in ps:
        if p.get("role") == "bed" and p.get("bg_db") == OLD:
            p["bg_db"] = BED_BG_DB
            n += 1
    return n


def run(root) -> dict[str, int]:
    out = {}
    eps = root / "episodes"
    for d in sorted(eps.iterdir()) if eps.is_dir() else []:
        f = d / MUSIC
        if not f.exists():
            continue
        doc = read_json(f)
        n = _fix(doc.get("placements", [])) + _fix((doc.get("draft") or {}).get("placements", []))
        if n:
            atomic_write_json(f, doc)
            out[d.name] = n
    (root / MARKER).write_text("done\n", encoding="utf-8")
    return out


def register(app, ctx) -> None:
    if not cloud.enabled() or (ctx.ws.root / MARKER).exists():
        return
    try:
        done = run(ctx.ws.root)
    except Exception:                  # the site must start; tried again at the next start
        log.exception("bed level: not put back")
        return
    log.warning("bed level back to %s dB: %s", BED_BG_DB, done)
