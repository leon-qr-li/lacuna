"""Fake API for 一键修复曲名 (lacuna_app/credit_fix.py): answers submit_credits for every file it is sent.
A file name with "乱" or "unknown" is not identified, one with "alt" gets two candidates (low confidence),
any other gets "Theme <name>" by 川井宪次, from 《午夜凶铃》 when the description says so."""
from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace


class FakeCreditFixAnthropic:
    def __init__(self, delay: float = 0.0, fail: bool = False):
        self.delay, self.fail, self.calls = delay, fail, []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.calls.append(kw)
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise RuntimeError("boom")
        info = json.loads(kw["messages"][0]["content"])
        desc = info.get("leons_description") or info.get("editors_description") or ""
        film = "午夜凶铃" if "午夜凶铃" in desc else None  # i18n-ignore
        items = []
        for f in info["files"]:
            stem = Path(f["file_name"] or "x").stem
            base = {"id": f["id"], "artist": None, "album": None, "year": None, "alternatives": []}
            if "乱" in stem or "unknown" in stem:  # i18n-ignore
                items.append(base | {"title": None, "composer": None, "film": None, "confidence": 0.1,
                                     "note": "没有线索，认不出来"})  # i18n-ignore
            elif "alt" in stem:
                items.append(base | {"title": "Curse", "composer": "川井宪次", "film": film, "confidence": 0.5,  # i18n-ignore
                                     "note": "两首时长都对得上", "alternatives": ["Video Tape — 川井宪次"]})  # i18n-ignore
            else:
                items.append(base | {"title": f"Theme {stem}", "composer": "川井宪次", "film": film,  # i18n-ignore
                                     "album": "Ringu OST" if film else None, "year": 1998 if film else None,
                                     "confidence": 0.9, "note": "时长对上原声带曲目表"})  # i18n-ignore
        usage = SimpleNamespace(input_tokens=2000, output_tokens=400, cache_read_input_tokens=0,
                                cache_creation_input_tokens=0)
        search = SimpleNamespace(type="web_search_tool_result",
                                 content=[SimpleNamespace(type="web_search_result", url="https://example.org/ringu-ost")])
        tool = SimpleNamespace(type="tool_use", name="submit_credits", input={"items": items})
        return SimpleNamespace(stop_reason="tool_use", content=[search, tool], usage=usage, model="claude-opus-5-5")
