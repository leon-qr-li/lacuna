"""一键修复曲名 (features/credit-fix): a fake lookup that takes a second, so the page shows it running."""
from pathlib import Path


def configure(mode: str, ws: Path, svc: dict) -> None:
    if mode != "default":
        return
    from tests.app.fake_credit_fix import FakeCreditFixAnthropic

    svc["credit_fix_client"] = FakeCreditFixAnthropic(delay=1.0)
