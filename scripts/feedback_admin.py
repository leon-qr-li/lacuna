"""用户反馈 from the server's command line, until the admin back office exists (decision 2026-10-24-user-feedback).

Leon picked this over a temporary page: Claude reads feedback and answers it for him on the server. A reply goes
through the app's own code (lacuna_app/feedback.py), so the person sees it exactly as from the admin later: the
status and reply in 我的反馈, the red dot, and the email in their language. Runs next to the live app (same site
database, nothing to stop). Inside the container the workspace comes from LACUNA_WORKSPACE.

    python scripts/feedback_admin.py list [--email someone@example.com] [--all]
    python scripts/feedback_admin.py show <id>
    python scripts/feedback_admin.py reply <id> [--text "…"] [--status planned] [--adopted yes|no] [--no-mail]
    python scripts/feedback_admin.py reset-prompts someone@example.com
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

try:
    import lacuna_app  # noqa: F401  (the installed app's own code, when run with its Python)
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lacuna_app import db as sitedb  # noqa: E402
from lacuna_app.auth import DEFAULT_SENDER, ResendMailer  # noqa: E402
from lacuna_app.feedback import STATUSES, Feedback, FeedbackError, reply_mail, status_name  # noqa: E402
from lacuna_app.i18n import speaking  # noqa: E402

ORIGIN = "https://lacunastudio.app"


def user(database: sitedb.DB, email: str) -> dict | None:
    r = database.query("SELECT data FROM users WHERE email = ?", (email,))
    return sitedb.loads(r[0]["data"]) if r else None


def sender(database: sitedb.DB) -> str:
    r = database.query("SELECT value FROM config WHERE key = 'sender'")
    return sitedb.loads(r[0]["value"]) if r else DEFAULT_SENDER


def when(t: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.gmtime(t)) + "Z"


def line(it: dict) -> str:
    text = (it["text"] or "—").replace("\n", " ")
    return f"{it['id']}  {when(it['created'])}  {it['kind']:<6} {it['status']:<9} {it['email']}  {text[:70]}"


def main(argv: list[str] | None = None, mailer=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", default=os.environ.get("LACUNA_WORKSPACE"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list")
    ls.add_argument("--email")
    ls.add_argument("--all", action="store_true", help="every item, not only the latest 30")
    sub.add_parser("show").add_argument("id")
    rp = sub.add_parser("reply")
    rp.add_argument("id")
    rp.add_argument("--text")
    rp.add_argument("--status", choices=STATUSES)
    rp.add_argument("--adopted", choices=["yes", "no"])
    rp.add_argument("--no-mail", action="store_true")
    sub.add_parser("reset-prompts").add_argument("email")
    args = ap.parse_args(argv)
    if not args.workspace:
        ap.error("--workspace (or LACUNA_WORKSPACE) is needed")
    database = sitedb.at(args.workspace)
    fb = Feedback(database, Path(args.workspace))

    if args.cmd == "list":
        items = [i for i in fb.all() if not args.email or i["email"] == args.email.strip().lower()]
        for it in items if args.all else items[:30]:
            print(line(it))
        print(f"({len(items)} in all)")
        return 0
    if args.cmd == "show":
        it = fb.get(args.id)
        if not it:
            print("no such feedback", file=sys.stderr)
            return 1
        sid = (it.get("show") or {}).get("id")
        it["profile"] = fb.profile(sid) if sid else None
        it["shot_file"] = str(fb.shot_path(args.id) or "")
        print(json.dumps(it, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "reset-prompts":
        email = args.email.strip().lower()
        if user(database, email) is None:
            print("no such account", file=sys.stderr)
            return 1
        fb.reset_prompts(email)
        print(f"reset: {email} is asked again after their next export")
        return 0

    # reply
    if not (args.text or args.status or args.adopted):
        ap.error("reply needs --text, --status or --adopted")
    try:
        it = fb.reply(args.id, args.text, args.status,
                      None if args.adopted is None else args.adopted == "yes")
    except FeedbackError as e:
        print(e, file=sys.stderr)
        return 1
    print(f"saved: {it['id']} now {it['status']} ({status_name(it['status'])})")
    person = user(database, it["email"])
    if args.no_mail or not person:
        return 0
    with speaking(person.get("lang") or "zh"):
        m = reply_mail(it, f"{ORIGIN}/#/feedback")
    (mailer or ResendMailer()).send(sender(database), it["email"], m["subject"], m["text"], html=m["html"],
                                    inline=m["inline"])
    print(f"mailed {it['email']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
