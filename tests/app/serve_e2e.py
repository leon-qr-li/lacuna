"""Start the app on a fresh synthetic workspace (used by Playwright's webServer)."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.app.synth import make_workspace  # noqa: E402
from lacuna_app.__main__ import main  # noqa: E402

if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv) > 1 else "8799"
    ws = make_workspace(Path(tempfile.mkdtemp(prefix="lacuna-e2e-")) / "ws")
    main(["--workspace", str(ws), "--port", port, "--no-browser", "--editor", "mock"])
