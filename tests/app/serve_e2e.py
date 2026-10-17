"""Start the app on a fresh synthetic workspace (used by Playwright's webServer).

    python tests/app/serve_e2e.py <port> [--ai]   # --ai: an AI first-cut episode, chat answered by a
                                                  # scripted fake Claude (tests/app/fake_claude.py)
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.app.synth import make_ai_workspace, make_workspace  # noqa: E402
from lacuna_app.__main__ import main  # noqa: E402

if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv) > 1 else "8799"
    if "--ai" in sys.argv:
        import uvicorn

        from lacuna_app.editor import ClaudeEditorAdapter
        from lacuna_app.server import create_app
        from tests.app.fake_claude import FakeAnthropic

        ws = make_ai_workspace(Path(tempfile.mkdtemp(prefix="lacuna-e2e-")) / "ws")
        uvicorn.run(create_app(ws, ClaudeEditorAdapter(client=FakeAnthropic())), host="127.0.0.1",
                    port=int(port), log_level="warning")
    else:
        ws = make_workspace(Path(tempfile.mkdtemp(prefix="lacuna-e2e-")) / "ws")
        main(["--workspace", str(ws), "--port", port, "--no-browser", "--editor", "mock"])
