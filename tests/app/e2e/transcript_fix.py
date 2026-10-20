"""校对专有名词 (decision `transcript-terms`): never a real request from E2E. The scopes server
(web/playwright.config.ts, SCOPES_PORT) gets a fake proofreader that reports 今天 as a mis-heard "Pei",
for web/e2e/transcript_fix.spec.ts (it proofreads the second episode, which no other spec reads words of)."""
import json
import os
from pathlib import Path
from types import SimpleNamespace


class _Proofread:
    def create(self, **kw):
        doc = json.loads(kw["messages"][0]["content"])
        fixes = [{"line": ln.split(" ", 1)[0], "wrong": "今天", "right": "Pei"}
                 for ln in doc["lines"] if "今天" in ln and "Pei" in doc["terms"]]
        return SimpleNamespace(stop_reason="end_turn", model="claude-sonnet-5-5", usage=None,
                               content=[SimpleNamespace(type="text", text=json.dumps({"fixes": fixes}, ensure_ascii=False))])


def configure(mode: str, ws: Path, svc: dict) -> None:
    from lacuna_app.transcript_fix import TranscriptFixer

    if mode == "default" and os.environ.get("LACUNA_E2E_SECOND_EPISODE"):
        svc["transcript_fixer"] = TranscriptFixer(client=SimpleNamespace(messages=_Proofread()))
    else:
        svc["transcript_fixer"] = TranscriptFixer(api_key="")
