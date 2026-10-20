"""去掉 um / uh (decision `english-fillers`): the scopes server (web/playwright.config.ts, SCOPES_PORT) also gets
an English copy of the synthetic episode with um / uh, for web/e2e/fillers.spec.ts."""
import os
from pathlib import Path


def configure(mode: str, ws: Path, svc: dict) -> None:
    if mode != "default" or not os.environ.get("LACUNA_E2E_SECOND_EPISODE"):
        return
    from tests.app.synth_en import make_en_workspace

    make_en_workspace(ws)
