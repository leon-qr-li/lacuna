"""校对专有名词 (decision `transcript-terms`): never a real request from E2E. The scopes server
(web/playwright.config.ts, SCOPES_PORT) gets an episode of its own and a fake proofreader that reports 今天 as a
mis-heard "Pei" in that episode only, for web/e2e/transcript_fix.spec.ts. Every episode opened there gets
proofread by itself; the others come back unchanged."""
import json
import os
from pathlib import Path
from types import SimpleNamespace

EPISODE = "EP_TEST_校对"
TITLE = "校对测试集"


class _Proofread:
    def create(self, **kw):
        doc = json.loads(kw["messages"][0]["content"])
        fixes = [{"line": ln.split(" ", 1)[0], "wrong": "今天", "right": "Pei"}
                 for ln in doc["lines"] if "今天" in ln and "Pei" in doc["terms"] and doc["episode_title"] == TITLE]
        return SimpleNamespace(stop_reason="end_turn", model="claude-sonnet-5-5", usage=None,
                               content=[SimpleNamespace(type="text", text=json.dumps({"fixes": fixes}, ensure_ascii=False))])


def configure(mode: str, ws: Path, svc: dict) -> None:
    from lacuna_app.transcript_fix import TranscriptFixer

    if mode == "default" and os.environ.get("LACUNA_E2E_SECOND_EPISODE"):
        from tests.app.synth import make_workspace

        make_workspace(ws, EPISODE)
        meta_p = ws / "episodes" / EPISODE / "episode.json"
        meta_p.write_text(json.dumps(json.loads(meta_p.read_text(encoding="utf-8")) | {"title": TITLE},
                                     ensure_ascii=False), encoding="utf-8")
        svc["transcript_fixer"] = TranscriptFixer(client=SimpleNamespace(messages=_Proofread()))
    else:
        svc["transcript_fixer"] = TranscriptFixer(api_key="")
