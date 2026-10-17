"""Import (phase 4): fake ASR and a fake Claude first cut on the import server."""
from pathlib import Path


def configure(mode: str, ws: Path, svc: dict) -> None:
    if mode != "import":
        return
    from lacuna_app.first_cut import ClaudeFirstCut
    from lacuna_app.importer import Importer
    from lacuna_app.store import Workspace
    from tests.app.fake_claude import FakeFirstCutAnthropic
    from tests.app.synth import fake_asr

    svc["importer"] = Importer(Workspace(ws).ensure(),
                               first_cut_factory=lambda: ClaudeFirstCut(client=FakeFirstCutAnthropic(delay=1.5)),
                               asr_backend=fake_asr)
