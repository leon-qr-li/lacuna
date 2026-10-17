"""Start the app on a fresh synthetic workspace (used by Playwright's webServer).

    python tests/app/serve_e2e.py <port> [--ai]   # --ai: an AI first-cut episode instead of the demo one
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.app.synth import make_ai_workspace, make_workspace  # noqa: E402
from lacuna_app.__main__ import main  # noqa: E402

if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv) > 1 else "8799"
    make = make_ai_workspace if "--ai" in sys.argv else make_workspace
    ws = make(Path(tempfile.mkdtemp(prefix="lacuna-e2e-")) / "ws")
    main(["--workspace", str(ws), "--port", port, "--no-browser", "--editor", "mock"])
