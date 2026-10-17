"""Start the app on a fresh synthetic workspace (used by Playwright's webServer).

    python tests/app/serve_e2e.py <port>          # synthetic episode
    python tests/app/serve_e2e.py <port> --ai     # an AI first-cut episode, chat answered by a scripted
                                                  # fake Claude (tests/app/fake_claude.py)
    python tests/app/serve_e2e.py <port> --import # empty workspace + two raw tracks in <ws>/recordings

Each feature's fakes are set up in its own module under tests/app/e2e/ (not here).
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.app.synth import make_ai_workspace, make_workspace, seed_learning, write_recordings  # noqa: E402


def main() -> None:
    import uvicorn

    from lacuna_app.editor import ClaudeEditorAdapter, MockEditorAdapter
    from lacuna_app.server import create_app
    from tests.app.e2e import configure_all
    from tests.app.fake_claude import FakeAnthropic

    port = sys.argv[1] if len(sys.argv) > 1 else "8799"
    mode = "import" if "--import" in sys.argv else "ai" if "--ai" in sys.argv else "default"
    tmp = Path(tempfile.mkdtemp(prefix="lacuna-e2e-")) / "ws"
    if mode == "import":
        ws = tmp
        write_recordings(ws / "recordings")
        adapter = MockEditorAdapter()
    elif mode == "ai":
        ws = Path(make_ai_workspace(tmp))
        seed_learning(ws)
        adapter = ClaudeEditorAdapter(client=FakeAnthropic())
    else:
        ws = Path(make_workspace(tmp))
        adapter = MockEditorAdapter()
    svc = configure_all(mode, ws, {})
    uvicorn.run(create_app(ws, adapter, **svc), host="127.0.0.1", port=int(port), log_level="warning")


if __name__ == "__main__":
    main()
