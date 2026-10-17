"""Start the app on a fresh synthetic workspace (used by Playwright's webServer).

    python tests/app/serve_e2e.py <port> [--ai]   # --ai: an AI first-cut episode, chat answered by a
                                                  # scripted fake Claude (tests/app/fake_claude.py)
    python tests/app/serve_e2e.py <port> --import # empty workspace + two raw tracks in <ws>/recordings;
                                                  # imports use a fake ASR and a fake Claude first cut
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.app.synth import make_ai_workspace, make_workspace, seed_learning  # noqa: E402
from lacuna_app.__main__ import main  # noqa: E402

if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv) > 1 else "8799"
    if "--import" in sys.argv:
        import uvicorn

        from lacuna_app.editor import MockEditorAdapter
        from lacuna_app.first_cut import ClaudeFirstCut
        from lacuna_app.importer import Importer
        from lacuna_app.server import create_app
        from lacuna_app.store import Workspace
        from tests.app.fake_claude import FakeFirstCutAnthropic
        from tests.app.synth import fake_asr, write_recordings

        root = Path(tempfile.mkdtemp(prefix="lacuna-e2e-")) / "ws"
        write_recordings(root / "recordings")
        ws = Workspace(root).ensure()
        imp = Importer(ws, first_cut_factory=lambda: ClaudeFirstCut(client=FakeFirstCutAnthropic(delay=1.5)),
                       asr_backend=fake_asr)
        uvicorn.run(create_app(root, MockEditorAdapter(), importer=imp), host="127.0.0.1", port=int(port),
                    log_level="warning")
    elif "--ai" in sys.argv:
        import uvicorn

        from lacuna_app.editor import ClaudeEditorAdapter
        from lacuna_app.server import create_app
        from tests.app.fake_claude import FakeAnthropic

        ws = make_ai_workspace(Path(tempfile.mkdtemp(prefix="lacuna-e2e-")) / "ws")
        seed_learning(ws)
        uvicorn.run(create_app(ws, ClaudeEditorAdapter(client=FakeAnthropic())), host="127.0.0.1",
                    port=int(port), log_level="warning")
    else:
        ws = make_workspace(Path(tempfile.mkdtemp(prefix="lacuna-e2e-")) / "ws")
        main(["--workspace", str(ws), "--port", port, "--no-browser", "--editor", "mock"])
