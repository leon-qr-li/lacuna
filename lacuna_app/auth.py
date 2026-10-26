"""Sign-in: accounts, roles, invites, two-step codes, sessions, email codes (via Resend).

Decisions: docs/decisions/2026-10-17-local-sign-in.md (the base), 2026-10-19-invites-roles-2fa.md (this).

- Passwords: scrypt with a random salt, checked locally, so signing in works offline.
- Invite-only: the first account (the owner) is created on the first run; every later account needs an
  invite link from the owner or an admin (one use, bound to one email, 7 days). There is no open sign-up.
- Roles: owner (one, can do everything), admin (invites and manages members), member.
- Two-step sign-in (TOTP from an authenticator app, lacuna_app/totp.py) plus 10 one-time recovery codes.
  Required for everyone when the app runs in the cloud (`cloud=True`); optional on the desktop app.
  Signing in is password -> short-lived ticket -> code -> session; no session exists before the code.
- Sessions: random tokens; only their SHA-256 is stored. "Remember me" = 30 days, else 12 hours. Each
  person sees their signed-in devices and can sign any of them out.
- Wrong password or code 5 times in 15 minutes locks the account for 15 minutes (and, in the cloud,
  30 failures from one address lock that address).
- Email codes (reset password): 6 digits, 10 minutes, 5 tries, one send per 60 s, in memory only. At most 5
  codes a day per email, none for an hour after one is guessed wrong 5 times, and at most 20 code requests an
  hour from one address (decision 2026-10-26-batch8-security-fixes).
  With two-step sign-in on, a reset also needs the authenticator (or a recovery code).
- In the cloud the first account also needs the setup code written to <root>/auth/setup-code.txt (and the
  server log) on the first start, so nobody who reaches a fresh server first can make themselves owner.
- Plans (lacuna_app/plans.py): every account has one (``plan``); its shows use its allowance.

Storage: the site database (lacuna_app/db.py): tables users, invites, config, sessions. The JSON files used
before (<workspace>/auth/users.json, sessions.json) are read once into it and left in place for 30 days.
Locked out with no email: delete the rows of the users table and the app asks for a new first account.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from . import db as sitedb
from . import legal, plans, totp
from .i18n import lang as ui_lang, normalize as norm_lang, speaking, tr
from .keystore import find_secret, save_secret
from .store import read_json

COOKIE = "lacuna_session"
REMEMBER_S = 30 * 86400
SHORT_S = 12 * 3600
CODE_S = 600
CODE_TRIES = 5
CODE_COOLDOWN_S = 60
CODES_PER_DAY = 5
CODE_BURNT_S = 3600      # after a code is guessed wrong CODE_TRIES times
IP_CODES_PER_HOUR = 20
LOGIN_TRIES = 5
LOCK_S = 15 * 60
IP_TRIES = 30
INVITE_S = 7 * 86400
TICKET_S = 300
SEEN_SAVE_S = 300
MIN_PASSWORD = 10
RESEND_KEY = "RESEND_API_KEY"
DEFAULT_SENDER = "LACUNA <noreply@lacunastudio.app>"   # domain verified in Resend (provision.py mail-domain)
TEST_SENDER_DOMAIN = "@resend.dev"   # Resend's test sender: only reaches the Resend sign-up email
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SCRYPT = dict(n=2 ** 14, r=8, p=1, maxmem=64 * 1024 * 1024, dklen=32)
RANK = {"member": 1, "admin": 2, "owner": 3}
SETUP_FILE = "setup-code.txt"
OLD_FILES = ("users.json", "users.json.bak", "sessions.json", "sessions.json.bak")
KEEP_OLD_S = 30 * 86400


def new_user_id() -> str:
    """The account's internal id: what the event log and the admin pages use instead of the email."""
    return "u_" + secrets.token_hex(6)


class AuthError(Exception):
    """A message for the person (already translated); `status` is the HTTP status to answer with."""

    def __init__(self, msg: str, status: int = 400):
        super().__init__(msg)
        self.status = status


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${_b64(salt)}${_b64(h)}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, h = stored.split("$")
        got = hashlib.scrypt(pw.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                             maxmem=64 * 1024 * 1024, dklen=len(base64.b64decode(h)))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, base64.b64decode(h))


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def clean_name(name: str | None) -> dict:
    """{"name": ...} for the name someone gave (spaces folded, 40 characters at most), {} for none."""
    n = " ".join(str(name or "").split())[:40]
    return {"name": n} if n else {}


def norm_email(email: str) -> str:
    e = (email or "").strip().lower()
    if not EMAIL_RE.match(e) or len(e) > 254:
        raise AuthError(tr("邮箱格式不对"))
    return e


def check_password(pw: str) -> None:
    if len(pw or "") < MIN_PASSWORD:
        raise AuthError(tr("密码至少要 {n} 位", n=MIN_PASSWORD))


# ------------------------------------------------------------------------------------------- mail

class MailError(Exception):
    pass


class ResendMailer:
    """Sends through the Resend HTTP API (https://resend.com/docs/api-reference/emails/send-email).
    The key is read on every send, so a key saved in 设置 works without a restart."""

    URL = "https://api.resend.com/emails"

    def __init__(self, key: Callable[[], str | None] = lambda: find_secret(RESEND_KEY)[0]):
        self._key = key

    def configured(self) -> bool:
        return bool(self._key())

    def send(self, sender: str, to: str, subject: str, text: str, html: str | None = None,
             inline: list[dict] | None = None) -> None:
        """`html`: the designed version next to `text`; `inline`: images it shows by ``cid:`` ({filename,
        content (bytes), content_id})."""
        key = self._key()
        if not key:
            raise MailError(tr("还没接上 Resend：先在「设置 → 邮件发件人」里填 Resend API key"))
        doc: dict = {"from": sender, "to": [to], "subject": subject, "text": text}
        if html:
            doc["html"] = html
        if inline:
            import base64
            doc["attachments"] = [{"filename": a["filename"], "content": base64.b64encode(a["content"]).decode(),
                                   "content_id": a["content_id"]} for a in inline]
        body = json.dumps(doc).encode()
        req = urllib.request.Request(self.URL, data=body, method="POST", headers={
            "Authorization": f"Bearer {key}", "Content-Type": "application/json",
            "User-Agent": "LACUNA-Studio"})   # Resend refuses urllib's default user agent
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                r.read()
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read().decode() or "{}").get("message", "")
            except (ValueError, OSError):
                detail = ""
            if e.code == 403 and "testing emails" in detail:
                raise MailError(tr("Resend 免费测试模式只能发到你注册 Resend 用的邮箱。要发给别的邮箱，先在 Resend 里验证自己的域名，再在设置里改发件地址。"))
            if e.code in (401, 403):
                raise MailError(tr("Resend 拒绝了这个 API key（{detail}）", detail=detail or e.code))
            raise MailError(tr("Resend 发信失败（{code}）：{detail}", code=e.code, detail=detail))
        except (urllib.error.URLError, OSError) as e:
            raise MailError(tr("连不上 Resend，检查一下网络（{e}）", e=getattr(e, "reason", e)))



# ------------------------------------------------------------------------------------------- store

class Auth:
    def __init__(self, root: Path, mailer=None, clock: Callable[[], float] = time.time, skip_setup: bool = False,
                 cloud: bool = False):
        self.dir = Path(root) / "auth"
        self.skip_setup = skip_setup     # E2E servers: don't force the first-account screen
        self.cloud = cloud               # require two-step sign-in, Secure cookies, setup code for the owner
        self.mailer = mailer if mailer is not None else ResendMailer()
        self.now = clock
        self.lock = threading.RLock()
        self.db = sitedb.at(root)
        now = self.now()
        if self.db.meta("auth_from_json") is None:
            self._from_json()
        self.users: dict[str, dict] = {r["email"]: sitedb.loads(r["data"]) for r in self.db.query("SELECT * FROM users")}
        self.config: dict = {"sender": DEFAULT_SENDER,
                             **{r["key"]: sitedb.loads(r["value"]) for r in self.db.query("SELECT * FROM config")}}
        if TEST_SENDER_DOMAIN in self.config["sender"]:   # saved before the domain was verified
            self.config["sender"] = DEFAULT_SENDER
        self.config.pop("allow_register", None)  # sign-up is by invite only now
        self.invites: dict[str, dict] = {r["hash"]: sitedb.loads(r["data"])
                                         for r in self.db.query("SELECT * FROM invites WHERE exp > ?", (now,))}
        self.sessions: dict[str, dict] = {r["hash"]: sitedb.loads(r["data"])
                                          for r in self.db.query("SELECT * FROM sessions WHERE exp > ?", (now,))}
        self._drop_old_files()
        self.codes: dict[tuple[str, str], dict] = {}
        self.code_sends: dict[str, list[float]] = {}   # email or "ip:<addr>" -> when codes were asked for
        self.code_burnt: dict[str, float] = {}         # email -> no new code before this time
        self.tickets: dict[str, dict] = {}        # password checked, waiting for the two-step code
        self.pending_totp: dict[str, dict] = {}   # signed in, setting up the authenticator
        self.fails: dict[str, list[float]] = {}
        self._seen_saved = now
        # other features follow accounts: joined(email, invite or None for the owner), deleted(email)
        self.on_joined: list[Callable[[str, dict | None], None]] = []
        # the site is in beta (routes/new_members.py: 「新成员需站长批准」 on): invite mails say so
        self.beta: Callable[[], bool] = lambda: False
        self.on_deleted: list[Callable[[str], None]] = []
        self.on_deleting: list[Callable[[str, dict, str], None]] = []    # (email, its record, who) before it goes
        self.setup_code: str | None = None
        if self.cloud and not self.users:
            self._make_setup_code()

    @property
    def require_2fa(self) -> bool:
        return self.cloud

    # -- persistence (the site database)
    def _from_json(self) -> None:
        """Once: the accounts kept in auth/users.json + sessions.json before the database move in. Everyone
        who had an account then keeps a free 专业版 (decision 2026-10-21-plans). The files stay 30 days."""
        f = self.dir / "users.json"
        data = (read_json(f) if f.exists() else None) or {}
        users = {u["email"]: u for u in data.get("users", [])}
        for u in users.values():                 # accounts from before roles: the first one is the owner
            u.setdefault("role", "owner" if u.pop("owner", False) else "member")
            u.pop("owner", None)
            u.setdefault("plan", plans.PRO)
            u.setdefault("plan_free", True)
        sess = read_json(self.dir / "sessions.json") if (self.dir / "sessions.json").exists() else None
        self.users, self.config = users, data.get("config", {})
        self.invites = {i["hash"]: i for i in data.get("invites", []) if i["exp"] > self.now()}
        self.sessions = {k: v for k, v in (sess or {}).get("sessions", {}).items() if v["exp"] > self.now()}
        self._save_users()
        self._save_sessions()
        self.db.set_meta("auth_from_json", str(self.now()))

    def _drop_old_files(self) -> None:
        """30 days after the move, the old JSON files go (until then a rollback to an older version finds them)."""
        moved = float(self.db.meta("auth_from_json") or 0)
        if moved and self.now() - moved > KEEP_OLD_S:
            for name in OLD_FILES:
                (self.dir / name).unlink(missing_ok=True)

    def _save_users(self) -> None:
        now = self.now()
        self.invites = {k: v for k, v in self.invites.items() if v["exp"] > now}
        for u in self.users.values():
            u.setdefault("id", new_user_id())
            u.setdefault("plan", plans.DEFAULT)
        with self.db.tx() as c:
            c.execute("DELETE FROM users")
            c.executemany("INSERT INTO users (email, id, role, plan, created, disabled, data) VALUES (?,?,?,?,?,?,?)",
                          [(u["email"], u["id"], u["role"], u["plan"], u["created"], int(bool(u.get("disabled"))),
                            sitedb.dumps(u)) for u in self.users.values()])
            c.execute("DELETE FROM invites")
            c.executemany("INSERT INTO invites (hash, email, exp, data) VALUES (?,?,?,?)",
                          [(i["hash"], i["email"], i["exp"], sitedb.dumps(i)) for i in self.invites.values()])
            c.execute("DELETE FROM config")
            c.executemany("INSERT INTO config (key, value) VALUES (?,?)",
                          [(k, sitedb.dumps(v)) for k, v in self.config.items()])

    def _save_sessions(self) -> None:
        with self.db.tx() as c:
            c.execute("DELETE FROM sessions")
            c.executemany("INSERT INTO sessions (hash, email, exp, data) VALUES (?,?,?,?)",
                          [(k, v["email"], v["exp"], sitedb.dumps(v)) for k, v in self.sessions.items()])
        self._seen_saved = self.now()

    def user_id(self, email: str | None) -> str | None:
        u = self.users.get(email or "")
        return u.get("id") if u else None

    def _make_setup_code(self) -> None:
        f = self.dir / SETUP_FILE
        if f.is_file() and f.read_text().strip():
            self.setup_code = f.read_text().strip()
        else:
            self.dir.mkdir(parents=True, exist_ok=True)
            self.setup_code = "-".join(secrets.token_hex(3) for _ in range(3))
            fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as fh:
                fh.write(self.setup_code + "\n")
        print(f"LACUNA setup code for the first account: {self.setup_code}  (also in {f})", flush=True)

    # -- queries
    def has_accounts(self) -> bool:
        return bool(self.users)

    def who(self, token: str | None) -> str | None:
        """The signed-in email for a session cookie, or None."""
        if not token:
            return None
        s = self.sessions.get(_sha(token))
        now = self.now()
        if not s or s["exp"] <= now:
            return None
        u = self.users.get(s["email"])
        if not u or u.get("disabled"):
            return None
        s["seen"] = now
        if now - self._seen_saved > SEEN_SAVE_S:
            with self.lock:
                self._save_sessions()
        return s["email"]

    def name(self, email: str | None) -> str | None:
        """The name the person gave (sign-up or 账号), or None."""
        return (self.users.get(email or "") or {}).get("name") or None

    def set_name(self, email: str, name: str) -> None:
        got = clean_name(name)
        if not got:
            raise AuthError(tr("请填你的名字"))
        with self.lock:
            self.users[email].update(got)
            self._save_users()

    def agree(self, email: str, version: str) -> None:
        """用户条款和隐私政策 (lacuna_app/legal.py): the signed-in person agreed to `version`, the current one."""
        got = legal.record(version, self.now())
        if not got:
            raise AuthError(tr("条款已经又更新了，请刷新页面再看一遍"), 409)
        with self.lock:
            self.users[email].update(got)
            self._save_users()

    def role(self, email: str | None) -> str | None:
        u = self.users.get(email or "")
        return u["role"] if u else None

    def status(self, token: str | None) -> dict:
        email = self.who(token)
        u = self.users.get(email or "")
        return {"accounts": self.has_accounts(), "setup": not self.users and not self.skip_setup,
                "email": email, "name": (u.get("name") or None) if u else None,
                "role": u["role"] if u else None, "plan": (u.get("plan") or plans.DEFAULT) if u else None,
                "twofa": bool(u and u.get("totp")), "require_2fa": self.require_2fa, "cloud": self.cloud,
                "first": not self.users, "setup_code": bool(self.setup_code) and not self.users,
                "mail": self.mail_status() if u and u["role"] == "owner" else None,
                "legal": {"version": legal.VERSION, "agreed": legal.agreed(u)}}

    def mail_status(self) -> dict:
        source = find_secret(RESEND_KEY)[1] if isinstance(self.mailer, ResendMailer) else "test"
        configured = self.mailer.configured()
        return {"configured": configured, "source": source if configured else None, "sender": self.config["sender"]}

    # -- failures and lockout
    def _check_lock(self, email: str, ip: str | None) -> None:
        now = self.now()
        for key, limit in ((email, LOGIN_TRIES), (f"ip:{ip}" if ip else None, IP_TRIES)):
            if not key:
                continue
            recent = self.fails[key] = [t for t in self.fails.get(key, []) if now - t < LOCK_S]
            if len(recent) >= limit:
                mins = max(1, math.ceil((LOCK_S - (now - recent[-limit])) / 60))
                raise AuthError(tr("错了太多次，{n} 分钟后再试", n=mins), 429)

    def _fail(self, email: str, ip: str | None) -> None:
        now = self.now()
        self.fails.setdefault(email, []).append(now)
        if ip:
            self.fails.setdefault(f"ip:{ip}", []).append(now)

    # -- sessions
    def _session(self, email: str, remember: bool, agent: str = "") -> tuple[str, int | None]:
        token = secrets.token_urlsafe(32)
        ttl = REMEMBER_S if remember else SHORT_S
        with self.lock:
            now = self.now()
            self.sessions = {k: v for k, v in self.sessions.items() if v["exp"] > now}
            self.sessions[_sha(token)] = {"email": email, "exp": now + ttl, "created": now, "seen": now,
                                          "agent": (agent or "")[:200]}
            self._save_sessions()
        return token, (ttl if remember else None)

    def logout(self, token: str | None) -> None:
        with self.lock:
            if token and self.sessions.pop(_sha(token), None) is not None:
                self._save_sessions()

    def list_sessions(self, email: str, token: str | None) -> list[dict]:
        cur = _sha(token or "")
        now = self.now()
        rows = [{"id": k[:16], "created": v["created"], "seen": v.get("seen", v["created"]), "agent": v.get("agent", ""),
                 "current": k == cur} for k, v in self.sessions.items() if v["email"] == email and v["exp"] > now]
        return sorted(rows, key=lambda r: (not r["current"], -r["seen"]))

    def end_sessions(self, email: str, token: str | None, sid: str | None = None) -> int:
        """Sign out one device of `email` (`sid` from list_sessions), or every other device (`sid` None)."""
        cur = _sha(token or "")
        with self.lock:
            drop = [k for k, v in self.sessions.items() if v["email"] == email and k != cur
                    and (sid is None or k[:16] == sid)]
            for k in drop:
                del self.sessions[k]
            if drop:
                self._save_sessions()
        return len(drop)

    def _end_all(self, email: str, keep: str | None = None) -> None:
        self.sessions = {k: v for k, v in self.sessions.items() if v["email"] != email or k == keep}
        self._save_sessions()

    def note_device(self, email: str, agent: str) -> bool:
        """Remember this browser + system for the account; True when it is new and the account had signed
        in elsewhere before (then the person gets a 新设备登录 email, lacuna_app/notice_mail.py)."""
        from .notice_mail import device_label
        key = _sha(device_label(agent))[:16]
        with self.lock:
            u = self.users.get(email)
            if not u:
                return False
            seen = u.setdefault("devices", [])
            if key in seen:
                return False
            seen.append(key)
            del seen[:-20]
            self._save_users()
            return len(seen) > 1

    # -- codes
    def send_code(self, email: str, purpose: str, ip: str | None = None) -> None:
        email = norm_email(email)
        if purpose != "reset":
            raise AuthError("bad purpose")
        now = self.now()
        if ip:      # counted for every email, known or not, so the limit says nothing about accounts
            asked = self.code_sends[f"ip:{ip}"] = [t for t in self.code_sends.get(f"ip:{ip}", []) if now - t < 3600]
            if len(asked) >= IP_CODES_PER_HOUR:
                raise AuthError(tr("验证码要得太频繁，{n} 分钟后再试", n=max(1, math.ceil((3600 - (now - asked[0])) / 60))), 429)
            asked.append(now)
        if email not in self.users or self.users[email].get("disabled"):
            return       # say nothing about which emails have accounts
        if self.code_burnt.get(email, 0) > now:
            raise AuthError(tr("验证码错了太多次，{n} 分钟后再试", n=max(1, math.ceil((self.code_burnt[email] - now) / 60))), 429)
        sent = self.code_sends[email] = [t for t in self.code_sends.get(email, []) if now - t < 86400]
        if len(sent) >= CODES_PER_DAY:
            raise AuthError(tr("今天的验证码已经发够了，明天再试，或联系 LACUNA 团队"), 429)
        old = self.codes.get((email, purpose))
        if old and now - old["sent"] < CODE_COOLDOWN_S:
            raise AuthError(tr("验证码刚发过，{n} 秒后再试", n=int(CODE_COOLDOWN_S - (now - old["sent"])) + 1), 429)
        code = f"{secrets.randbelow(10 ** 6):06d}"
        try:
            self.mailer.send(self.config["sender"], email, tr("LACUNA 验证码：{code}", code=code),
                             tr("你的验证码是 {code}，10 分钟内有效，用于{what}。\n\n如果不是你本人操作，忽略这封邮件即可。",
                                code=code, what=tr("重设 LACUNA 密码")))
        except MailError as e:
            raise AuthError(str(e), 502)
        self.codes[(email, purpose)] = {"hash": _sha(code), "exp": now + CODE_S, "tries": 0, "sent": now}
        sent.append(now)

    def _use_code(self, email: str, purpose: str, code: str) -> None:
        c = self.codes.get((email, purpose))
        if not c or c["exp"] <= self.now():
            raise AuthError(tr("验证码过期了，重新发一个"))
        c["tries"] += 1
        if not hmac.compare_digest(c["hash"], _sha((code or "").strip())):
            if c["tries"] >= CODE_TRIES:
                del self.codes[(email, purpose)]
                self.code_burnt[email] = self.now() + CODE_BURNT_S
                raise AuthError(tr("验证码错了太多次，1 小时后再重新发一个"))
            raise AuthError(tr("验证码不对"))
        del self.codes[(email, purpose)]

    # -- the step after the password
    def _next_step(self, email: str, remember: bool, agent: str, then: dict | None = None) -> dict:
        """Password (or invite, or email code) accepted: a session, or a ticket for the two-step code."""
        u = self.users[email]
        if u.get("totp") or self.require_2fa:
            ticket = secrets.token_urlsafe(24)
            now = self.now()
            self.tickets = {k: v for k, v in self.tickets.items() if v["exp"] > now}
            t = {"email": email, "remember": remember, "agent": agent, "exp": now + TICKET_S, "then": then or {}}
            if u.get("totp"):
                self.tickets[ticket] = t | {"kind": "2fa"}
                return {"step": "2fa", "ticket": ticket}
            secret = totp.new_secret()
            self.tickets[ticket] = t | {"kind": "enroll", "secret": secret}
            return {"step": "enroll", "ticket": ticket, "secret": secret, "uri": totp.uri(secret, email)}
        self._apply(email, then or {})
        return {"step": "done", "session": self._session(email, remember, agent)}

    def _apply(self, email: str, then: dict) -> None:
        if then.get("hash"):          # a password reset waiting for the two-step code
            with self.lock:
                self.users[email]["hash"] = then["hash"]
                self.users[email]["verified"] = True
                self._end_all(email)
                self._save_users()

    def _ticket(self, ticket: str, kind: str) -> dict:
        t = self.tickets.get(ticket or "")
        if not t or t["exp"] <= self.now() or t["kind"] != kind or t["email"] not in self.users:
            self.tickets.pop(ticket or "", None)
            raise AuthError(tr("这一步等太久了，请重新登录"), 401)
        return t

    def _second_factor(self, u: dict, code: str) -> bool:
        """An authenticator code (not reused) or an unused recovery code; uses it up."""
        tf = u.get("totp") or {}
        step = totp.match(tf.get("secret", ""), code, self.now(), tf.get("last", -1)) if tf else None
        if step is not None:
            tf["last"] = step
            self._save_users()
            return True
        rc = totp.norm_recovery(code)
        hashes = u.get("recovery", [])
        if rc and _sha(rc) in hashes:
            hashes.remove(_sha(rc))
            self._save_users()
            return True
        return False

    def second_step(self, ticket: str, code: str, ip: str | None = None) -> dict:
        t = self._ticket(ticket, "2fa")
        email = t["email"]
        self._check_lock(email, ip)
        with self.lock:
            ok = self._second_factor(self.users[email], code)
        if not ok:
            self._fail(email, ip)
            raise AuthError(tr("两步验证码不对"), 401)
        self.tickets.pop(ticket, None)
        self.fails.pop(email, None)
        self._apply(email, t["then"])
        return {"step": "done", "session": self._session(email, t["remember"], t["agent"])}

    def enroll(self, ticket: str, code: str, ip: str | None = None) -> dict:
        """First sign-in where two-step is required: confirm the authenticator, get recovery codes."""
        t = self._ticket(ticket, "enroll")
        email = t["email"]
        self._check_lock(email, ip)
        step = totp.match(t["secret"], code, self.now())
        if step is None:
            self._fail(email, ip)
            raise AuthError(tr("两步验证码不对：看一下手机上 LACUNA 这一项现在的 6 位数字"), 401)
        self.tickets.pop(ticket, None)
        codes = self._turn_on(email, t["secret"], step)
        self._apply(email, t["then"])
        return {"step": "done", "session": self._session(email, t["remember"], t["agent"]), "recovery": codes}

    def _turn_on(self, email: str, secret: str, step: int) -> list[str]:
        codes = totp.recovery_codes()
        with self.lock:
            u = self.users[email]
            u["totp"] = {"secret": secret, "since": self.now(), "last": step}
            u["recovery"] = [_sha(c) for c in codes]
            self._save_users()
        return codes

    # -- two-step settings (signed in)
    def start_2fa(self, email: str) -> dict:
        secret = totp.new_secret()
        self.pending_totp[email] = {"secret": secret, "exp": self.now() + 15 * 60}
        return {"secret": secret, "uri": totp.uri(secret, email)}

    def confirm_2fa(self, email: str, code: str) -> list[str]:
        p = self.pending_totp.get(email)
        if not p or p["exp"] <= self.now():
            raise AuthError(tr("这一步等太久了，重新点「开启两步验证」"))
        step = totp.match(p["secret"], code, self.now())
        if step is None:
            raise AuthError(tr("两步验证码不对：看一下手机上 LACUNA 这一项现在的 6 位数字"))
        del self.pending_totp[email]
        return self._turn_on(email, p["secret"], step)

    def _check_own_code(self, email: str, code: str) -> None:
        self._check_lock(email, None)
        with self.lock:
            ok = self._second_factor(self.users[email], code)
        if not ok:
            self._fail(email, None)
            raise AuthError(tr("两步验证码不对"))

    def new_recovery(self, email: str, code: str) -> list[str]:
        u = self.users[email]
        if not u.get("totp"):
            raise AuthError(tr("还没开两步验证"))
        self._check_own_code(email, code)
        codes = totp.recovery_codes()
        with self.lock:
            u["recovery"] = [_sha(c) for c in codes]
            self._save_users()
        return codes

    def disable_2fa(self, email: str, code: str) -> None:
        if self.require_2fa:
            raise AuthError(tr("每个账号都必须开两步验证"), 403)
        self._check_own_code(email, code)
        with self.lock:
            self.users[email].pop("totp", None)
            self.users[email].pop("recovery", None)
            self._save_users()

    def change_password(self, email: str, old: str, new: str, token: str | None) -> None:
        check_password(new)
        self._check_lock(email, None)
        if not verify_password(old or "", self.users[email]["hash"]):
            self._fail(email, None)
            raise AuthError(tr("现在的密码不对"))
        with self.lock:
            self.users[email]["hash"] = hash_password(new)
            self._end_all(email, keep=_sha(token or ""))   # other devices sign in again
            self._save_users()

    # -- accounts
    def register_first(self, email: str, password: str, setup_code: str | None, remember: bool,
                       agent: str = "", proven: str | None = None, name: str = "", agreed: str | None = None) -> dict:
        """The owner's account, on the first run (no invite; in the cloud, the setup code, unless Cloudflare
        Access already proved the request comes from `proven`, the owner's email, and that is the email given)."""
        email = norm_email(email)
        check_password(password)
        with self.lock:
            if self.users:
                raise AuthError(tr("只能通过邀请链接注册。请向 LACUNA 的管理员要一个邀请。"), 403)
            if self.setup_code and proven != email and not hmac.compare_digest(self.setup_code, (setup_code or "").strip().lower()):
                raise AuthError(tr("初始化码不对：在服务器上的 auth/setup-code.txt 里"), 403)
            self.users[email] = {"email": email, "hash": hash_password(password), "created": self.now(),
                                 "role": "owner", "verified": False, "id": new_user_id(), "plan": plans.PRO,
                                 "plan_free": True, **clean_name(name), **legal.record(agreed, self.now())}
            self._save_users()
            if self.setup_code:
                (self.dir / SETUP_FILE).unlink(missing_ok=True)
                self.setup_code = None
        for f in self.on_joined:
            f(email, None)
        return self._next_step(email, remember, agent)

    def invite_info(self, token: str) -> dict:
        i = self.invites.get(_sha(token or ""))
        if not i or i["exp"] <= self.now() or i["email"] in self.users:
            raise AuthError(tr("这个邀请链接已经失效（用过了、过期了或被撤回了）。请向邀请你的人要一个新的。"), 404)
        return i

    def register_invite(self, token: str, password: str, remember: bool, agent: str = "", name: str = "",
                        agreed: str | None = None) -> dict:
        check_password(password)
        with self.lock:
            i = self.invite_info(token)
            email = i["email"]
            self.users[email] = {"email": email, "hash": hash_password(password), "created": self.now(),
                                 "role": i["role"], "verified": True, "invited_by": i["by"], "id": new_user_id(),
                                 "plan": plans.check(i.get("plan") or plans.DEFAULT), "lang": i.get("lang"),
                                 **clean_name(name), **legal.record(agreed, self.now())}
            del self.invites[i["hash"]]
            self._save_users()
        for f in self.on_joined:
            f(email, i)
        return self._next_step(email, remember, agent)

    def login(self, email: str, password: str, remember: bool, ip: str | None = None, agent: str = "") -> dict:
        email = (email or "").strip().lower()
        self._check_lock(email, ip)
        u = self.users.get(email)
        if not u or not verify_password(password or "", u["hash"]) or u.get("disabled"):
            self._fail(email, ip)
            raise AuthError(tr("邮箱或密码不对"), 401)
        if not u.get("totp"):
            self.fails.pop(email, None)
        return self._next_step(email, remember, agent)

    def reset(self, email: str, code: str, password: str, agent: str = "") -> dict:
        email = norm_email(email)
        check_password(password)
        if email not in self.users or self.users[email].get("disabled"):
            raise AuthError(tr("验证码过期了，重新发一个"))
        self._use_code(email, "reset", code)
        self.fails.pop(email, None)
        return self._next_step(email, True, agent, then={"hash": hash_password(password)})

    # -- members (owner / admin)
    def _manage(self, actor: str, target: str) -> dict:
        a, u = self.users.get(actor), self.users.get(target)
        if not u:
            raise AuthError(tr("没有这个账号"), 404)
        if actor == target or not a or RANK[a["role"]] <= RANK[u["role"]]:
            raise AuthError(tr("你没有权限改这个账号"), 403)
        return u

    def _grantable(self, actor: str, role: str) -> None:
        if role not in ("admin", "member") or RANK[self.users[actor]["role"]] <= RANK[role]:
            raise AuthError(tr("你没有权限给这个角色"), 403)

    def list_users(self) -> list[dict]:
        last: dict[str, float] = {}
        for v in self.sessions.values():
            last[v["email"]] = max(last.get(v["email"], 0), v.get("seen", v["created"]))
        rows = [{"email": u["email"], "role": u["role"], "created": u["created"], "twofa": bool(u.get("totp")),
                 "disabled": bool(u.get("disabled")), "seen": last.get(u["email"]),
                 "plan": u.get("plan") or plans.DEFAULT} for u in self.users.values()]
        return sorted(rows, key=lambda r: (-RANK[r["role"]], r["created"]))

    def update_user(self, actor: str, target: str, role: str | None = None, disabled: bool | None = None,
                    reset_2fa: bool = False, plan: str | None = None) -> None:
        with self.lock:
            if plan is not None:
                self.set_plan(actor, target, plan)
                if role is None and disabled is None and not reset_2fa:
                    return
            u = self._manage(actor, target)
            if role is not None:
                self._grantable(actor, role)
                u["role"] = role
            if disabled is not None:
                u["disabled"] = bool(disabled)
                if disabled:
                    self._end_all(target)
            if reset_2fa:            # lost phone and recovery codes: they set it up again at next sign-in
                u.pop("totp", None)
                u.pop("recovery", None)
                self._end_all(target)
            self._save_users()

    def set_plan(self, actor: str, target: str, plan: str) -> None:
        """Site owner and admins set anyone's plan, their own too (nobody pays yet: decision 2026-10-21-plans)."""
        if plan not in plans.PLANS:
            raise AuthError(tr("没有这个套餐"))
        with self.lock:
            a, u = self.users.get(actor), self.users.get(target)
            if not u:
                raise AuthError(tr("没有这个账号"), 404)
            if not a or RANK[a["role"]] < RANK["admin"]:
                raise AuthError(tr("你没有权限改这个账号"), 403)
            u["plan"] = plan
            u.pop("plan_free", None)
            self._save_users()

    def delete_user(self, actor: str, target: str) -> None:
        """Removes the account only; what they made stays where it is."""
        with self.lock:
            self._manage(actor, target)
            for f in self.on_deleting:
                f(target, dict(self.users[target]), actor)
            del self.users[target]
            self._end_all(target)
            self._save_users()
        for f in self.on_deleted:
            f(target)

    def restore_user(self, record: dict) -> None:
        """A deleted account back from the 回收区 (trash.py), as it was; it signs in again."""
        with self.lock:
            if record["email"] in self.users:
                raise AuthError(tr("这个邮箱已经有账号了"), 409)
            self.users[record["email"]] = record
            self._save_users()

    # -- invites (owner / admin)
    def list_invites(self) -> list[dict]:
        now = self.now()
        return sorted(({"id": i["hash"][:16], "email": i["email"], "role": i["role"], "by": i["by"],
                        "plan": i.get("plan") or plans.DEFAULT,
                        "created": i["created"], "exp": i["exp"], "space": i.get("space"),
                        "space_role": i.get("space_role")} for i in self.invites.values() if i["exp"] > now),
                      key=lambda r: -r["created"])

    def invite(self, actor: str, email: str, role: str, origin: str, extra: dict | None = None,
               lang: str | None = None, by_member: bool = False) -> dict:
        """A one-time sign-up link for `email`; emailed when Resend can, always returned for copying.
        `lang` (zh / en) is the email's language, picked by the inviter; default the inviter's interface.
        `by_member`: a show's admin inviting a collaborator into that show (routes/spaces.py checks the show
        and the plan), so a plain account may give the plain "member" role."""
        email = norm_email(email)
        if not (by_member and role == "member" and actor in self.users):
            self._grantable(actor, role)
        if (extra or {}).get("plan") not in (None, *plans.PLANS):
            raise AuthError(tr("没有这个套餐"))
        if email in self.users:
            raise AuthError(tr("这个邮箱已经有账号了"), 409)
        token = secrets.token_urlsafe(32)
        now = self.now()
        lang = norm_lang(lang) or ui_lang()
        extra = dict(extra or {})
        project = extra.pop("space_name", None)          # for the email only
        with self.lock:
            self.invites = {k: v for k, v in self.invites.items() if v["email"] != email}   # the newest link wins
            self.invites[_sha(token)] = {"hash": _sha(token), "email": email, "role": role, "by": actor,
                                         "created": now, "exp": now + INVITE_S, "lang": lang, **extra}
            self._save_users()
        # in the path, not after "#": Cloudflare Access's sign-in drops a URL's #fragment on the way back
        link = f"{origin.rstrip('/')}/invite/{token}"
        mailed, why = False, None
        try:
            from . import invite_mail       # design A 「夜航信笺」
            with speaking(lang):
                m = invite_mail.render(actor, link, project, extra.get("space_role"),
                                       plan=extra.get("plan") or plans.DEFAULT, beta=self.beta(),
                                       inviter_name=(self.users.get(actor) or {}).get("name"))
            try:
                self.mailer.send(self.config["sender"], email, m["subject"], m["text"], html=m["html"],
                                 inline=m["inline"])
            except MailError:           # the designed one refused: the plain one still gets the link there
                self.mailer.send(self.config["sender"], email, m["subject"], m["text"])
            mailed = True
        except MailError as e:
            why = str(e)
        return {"link": link, "mailed": mailed, "mail_error": why, "email": email, "role": role}

    def add_join(self, email: str, space: str, space_role: str) -> bool:
        """`email` has a sign-up link waiting: they also join `space` when they use it (a show admin invited
        someone the site already invited). False when there is no such link."""
        email = norm_email(email)
        now = self.now()
        with self.lock:
            found = [i for i in self.invites.values() if i["email"] == email and i["exp"] > now]
            if not found:
                return False
            also = [j for j in found[0].get("also", []) if j.get("space") != space]
            found[0]["also"] = also + [{"space": space, "space_role": space_role}]
            self._save_users()
        return True

    def revoke_invite(self, iid: str) -> list[str]:
        """Withdraws the invite; returns the email(s) it was for."""
        with self.lock:
            gone = [k for k in self.invites if k[:16] == iid]
            emails = [self.invites.pop(k)["email"] for k in gone]
            self._save_users()
        return emails

    # -- settings (owner)
    def update_config(self, sender: str | None = None) -> None:
        with self.lock:
            if sender is not None:
                s = sender.strip() or DEFAULT_SENDER
                if "@" not in s:
                    raise AuthError(tr("发件地址要包含邮箱，例如 LACUNA <noreply@你的域名>"))
                self.config["sender"] = s
            self._save_users()

    def save_resend_key(self, key: str) -> str:
        key = key.strip().strip('"')
        if not key.startswith("re_") or len(key) < 20 or any(c.isspace() for c in key):
            raise AuthError(tr("这不像 Resend 的 API key（应该是 re_ 开头的一长串）"))
        try:
            return save_secret(RESEND_KEY, key)
        except OSError as e:
            raise AuthError(tr("保存失败：{e}", e=e), 500)

    def test_mail(self, email: str) -> None:
        try:
            self.mailer.send(self.config["sender"], email, tr("LACUNA 测试邮件"),
                             tr("Resend 已经接好了：LACUNA 能给你发验证码了。"))
        except MailError as e:
            raise AuthError(str(e), 502)
