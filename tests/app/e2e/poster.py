"""Cover (phase 10): covers drawn by a scripted fake Claude."""
from pathlib import Path


def configure(mode: str, ws: Path, svc: dict) -> None:
    if mode != "default":
        return
    from lacuna_app.poster import ClaudeDesigner, Posters
    from lacuna_app.store import Workspace
    from tests.app.fake_claude import FakePosterAnthropic

    svc["posters"] = Posters(Workspace(ws), svc["publisher"],
                             lambda: ClaudeDesigner(client=FakePosterAnthropic(delay=0.5)))
