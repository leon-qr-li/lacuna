"""Library scopes (公共 / 本集): the fourth E2E server (web/playwright.config.ts, SCOPES_PORT) is the
default workspace plus a second episode, so web/e2e/library_scopes.spec.ts can check that a music
page leaves out another episode's music. The other default-mode servers are untouched."""
import json
import os
from pathlib import Path

SECOND_EPISODE = "EP_TEST_另一集"
SECOND_TITLE = "另一集（范围测试）"


def configure(mode: str, ws: Path, svc: dict) -> None:
    if mode != "default" or not os.environ.get("LACUNA_E2E_SECOND_EPISODE"):
        return
    from tests.app.synth import make_workspace

    make_workspace(ws, SECOND_EPISODE)
    meta_p = ws / "episodes" / SECOND_EPISODE / "episode.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    meta["title"] = SECOND_TITLE
    meta_p.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
