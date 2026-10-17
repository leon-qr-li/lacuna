"""Publish pack (phase 9): answered by a scripted fake Claude."""
from pathlib import Path

ORDER = 10      # the cover module builds on this publisher


def configure(mode: str, ws: Path, svc: dict) -> None:
    if mode == "import":
        return
    from lacuna_app.publish import ClaudePublisher, Publisher
    from lacuna_app.store import Workspace
    from tests.app.fake_claude import FakePublishAnthropic

    delay = 1.0 if mode == "ai" else 0.0
    svc["publisher"] = Publisher(Workspace(ws), lambda: ClaudePublisher(client=FakePublishAnthropic(delay=delay)))
