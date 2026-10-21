"""Sign-in (lacuna_app/auth.py) on the default server: a fake mailer whose outbox the spec reads through
/api/auth/_test/outbox, and /api/auth/_test/reset?skip_setup=… so the spec leaves the shared server without accounts."""
from pathlib import Path


class FakeMailer:
    def __init__(self):
        self.outbox: list[dict] = []

    def configured(self) -> bool:
        return True

    def send(self, sender: str, to: str, subject: str, text: str, html: str | None = None, inline: list | None = None) -> None:
        self.outbox.append({"from": sender, "to": to, "subject": subject, "text": text, "html": html,
                            # inline images without their bytes (the outbox is served as JSON to the E2E tests)
                            "inline": [{"filename": a["filename"], "content_id": a["content_id"],
                                        "png": a["content"][:8] == b"\x89PNG\r\n\x1a\n"} for a in inline or []]})


def configure(mode: str, ws: Path, svc: dict) -> None:
    # the other specs use the app without signing in: no first-account screen on any E2E server
    svc["auth_skip_setup"] = True
    if mode != "default":
        return
    svc["mailer"] = FakeMailer()
    svc["auth_test_reset"] = True
    svc["mail_inline"] = True          # notice mails (new device, 申请试用) land in the outbox before the answer
