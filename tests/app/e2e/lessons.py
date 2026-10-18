"""Confirmed learning (首次检测 #9, #12): 「记住」 drafts and 本集学到的规则 answered by a scripted writer."""
from pathlib import Path


def configure(mode: str, ws: Path, svc: dict) -> None:
    from tests.app.fake_lessons import FakeRuleWriter

    svc["rule_writer"] = FakeRuleWriter(delay=0.4)
