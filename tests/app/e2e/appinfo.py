"""设置 page (phase 7): the import server runs as installed 2026.10.17.1 with a local feed offering 2026.10.18.1."""
from pathlib import Path


def configure(mode: str, ws: Path, svc: dict) -> None:
    if mode != "import":
        return
    from lacuna_app.appinfo import Updater
    from tests.app.test_appinfo import make_feed

    tmp = Path(ws).parent
    svc["updater"] = Updater(home=tmp / "home", feed_url=make_feed(tmp, "2026.10.18.1"), version="2026.10.17.1")
