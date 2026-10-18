"""AI first-cut windows are cached atomically, and a window file torn by a crash is cut again on
「继续」 instead of failing every retry."""
import shutil

import pytest

from lacuna_app.ai_cut import TrackTokens
from lacuna_app.first_cut import ClaudeFirstCut
from lacuna_app.importer import Importer
from lacuna_app.store import Workspace, read_json

from .fake_claude import FakeFirstCutAnthropic
from .synth import fake_asr, write_recordings

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


def test_torn_window_cache_is_cut_again(tmp_path):
    rec = write_recordings(tmp_path / "rec")
    ws = Workspace(tmp_path / "ws").ensure()
    fake = FakeFirstCutAnthropic()
    imp = Importer(ws, first_cut_factory=lambda: ClaudeFirstCut(client=fake), asr_backend=fake_asr)
    imp.start("EP002", "", str(rec["Leon"]), str(rec["Pei"]), wait=True)
    assert imp.status("EP002")["state"] == "done"
    d = imp.dir_for("EP002")
    win = d / "ai_windows" / "window_00.json"
    good = read_json(win)
    assert good["ops"] and len(fake.requests) == 1

    doc = (d / "editor_input.md").read_text(encoding="utf-8")
    tokens = {tag: TrackTokens(t) for tag, t in read_json(d / "tokens.json")["tracks"].items()}
    fc = ClaudeFirstCut(client=fake)
    fc.run(doc, 60.0, tokens, "EP002", cache_dir=d / "ai_windows")
    assert len(fake.requests) == 1                      # a sound cache is reused

    win.write_text(win.read_text(encoding="utf-8")[:40], encoding="utf-8")    # torn mid-write
    for bak in win.parent.glob("*.bak"):
        bak.unlink()
    res = fc.run(doc, 60.0, tokens, "EP002", cache_dir=d / "ai_windows")
    assert len(fake.requests) == 2 and res.ops_doc["ops"]
    assert read_json(win)["ops"] == good["ops"]
