"""Credit lookups that overlap (backlog item 14): a note like "并发 A 慢" makes the fake answer after a
pause with a title taken from the note, so two lookups started together are both in flight at once.
Any other note goes to the wrapped fake (tests/app/fake_claude.py FakeCreditAnthropic)."""
from __future__ import annotations

import json
import re
import time
from types import SimpleNamespace


class OverlappingCreditFake:
    def __init__(self, base, slow: float = 1.5):
        self.base, self.slow = base, slow
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kw):
        note = json.loads(kw["messages"][0]["content"]).get("leons_note") or ""
        m = re.match(r"并发 (\w+)( 慢)?", note)
        if not m:
            return self.base.beta.messages.create(**kw)
        time.sleep(self.slow if m.group(2) else self.slow / 3)
        usage = SimpleNamespace(input_tokens=1000, output_tokens=200, cache_read_input_tokens=0,
                                cache_creation_input_tokens=0)
        found = {"title": f"Concurrent Theme {m.group(1)}", "artist": None, "composer": "Test Composer", "album": None,
                 "film": None, "year": 2020, "confidence": 0.9, "note": ""}
        return SimpleNamespace(stop_reason="tool_use", model="claude-haiku-5-5", usage=usage,
                               content=[SimpleNamespace(type="tool_use", name="submit_credit", input=found)])
