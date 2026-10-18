"""Media library (phase 6a): music files to drag / pick, and a fake credit lookup and music chat."""
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def configure(mode: str, ws: Path, svc: dict) -> None:
    if mode != "default":
        return
    from tests.app.fake_claude import FakeCreditAnthropic
    from tests.app.fake_credit import OverlappingCreditFake
    from tests.app.fake_music import FakeMusicAnthropic
    from tests.app.synth import write_music_inbox

    # music files for the media library E2E to drag / pick (web/e2e/music.spec.ts reads them here)
    write_music_inbox(REPO / "web" / "e2e" / ".fixtures" / "music_inbox")
    svc["credit_client"] = OverlappingCreditFake(FakeCreditAnthropic())   # notes "并发 …": overlapping lookups
    svc["music_client"] = FakeMusicAnthropic()     # "间奏晚两秒" / "小 3 dB" / "片尾去掉" on the music page
