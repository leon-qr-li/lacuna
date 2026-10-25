"""Site-wide AI switches the owner flips in the admin area (系统健康 → AI 省钱), stored in the site database's
meta table like the retention rules (retention.py). Decision 2026-10-25-ai-cost-cut:

* first_cut_batch: send the AI first cut through the Batch API (half price). Imports wait longer, usually 10-30
  minutes and sometimes hours at peak, so it is off; turn it on when cost matters more than speed.
"""
from __future__ import annotations

import json

SETTINGS_KEY = "ai"
DEFAULTS = {"first_cut_batch": False}


def settings(db) -> dict:
    try:
        saved = json.loads(db.meta(f"admin:{SETTINGS_KEY}") or "{}")
    except ValueError:
        saved = {}
    return DEFAULTS | {k: bool(v) for k, v in (saved or {}).items() if k in DEFAULTS}


def save_settings(db, changes: dict) -> dict:
    from . import db as sitedb
    s = settings(db) | {k: bool(v) for k, v in changes.items() if k in DEFAULTS}
    db.set_meta(f"admin:{SETTINGS_KEY}", sitedb.dumps(s))
    return s
