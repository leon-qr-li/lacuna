"""The real app on a rehearsal workspace: real ASR, real audio engine, fake Claude everywhere.

    python scripts/rehearsal/serve.py <workspace> <models-dir> [--port 8790]

Every step that calls the Claude API (first cut, chat, publish pack, cover, credit lookup) is
answered by a scripted fake, so the rehearsal needs no key and sends nothing anywhere.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> None:
    import uvicorn

    from lacuna_app.editor import ClaudeEditorAdapter
    from lacuna_app.first_cut import ClaudeFirstCut
    from lacuna_app.importer import Importer
    from lacuna_app.poster import ClaudeDesigner, Posters
    from lacuna_app.publish import ClaudePublisher, Publisher
    from lacuna_app.server import create_app
    from lacuna_app.store import Workspace
    from scripts.rehearsal.fake_first_cut import FakeLongFirstCut
    from tests.app.fake_claude import (FakeAnthropic, FakeCreditAnthropic, FakePosterAnthropic,
                                       FakePublishAnthropic)

    ap = argparse.ArgumentParser()
    ap.add_argument("workspace", type=Path)
    ap.add_argument("models", type=Path)
    ap.add_argument("--port", type=int, default=8790)
    a = ap.parse_args()
    ws = Workspace(a.workspace).ensure()
    publisher = Publisher(ws, lambda: ClaudePublisher(client=FakePublishAnthropic(delay=2.0)))
    svc = dict(
        importer=Importer(ws, first_cut_factory=lambda: ClaudeFirstCut(client=FakeLongFirstCut(ws.root)),
                          models_dir=a.models),
        publisher=publisher,
        posters=Posters(ws, publisher, lambda: ClaudeDesigner(client=FakePosterAnthropic(delay=1.0))),
        credit_client=FakeCreditAnthropic())
    app = create_app(ws.root, ClaudeEditorAdapter(client=FakeAnthropic()), **svc)
    uvicorn.run(app, host="127.0.0.1", port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
