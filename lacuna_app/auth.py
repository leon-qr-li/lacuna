"""Sign-in for the local app: accounts, sessions, email codes (via Resend).

Threat model (docs/decisions/2026-10-17-local-sign-in.md): the server only listens on 127.0.0.1, so
sign-in does not protect the files on disk from someone at the computer. What it adds: a person who
opens the app must know the password, and other websites in the browser can no longer drive the local
API (the session cookie is SameSite=Strict and every /api call needs it once an account exists).

- Passwords: scrypt with a random salt, checked locally, so signing in works offline.
- Sessions: random tokens; only their SHA-256 is stored. "Remember me" = 30 days, else 12 hours.
- Email codes (register, reset password): 6 digits, 10 minutes, 5 tries, one send per 60 s.
  They live in memory only (a restart forgets them; ask for a new one).
- Until the first account exists the API stays open, and that first account needs no code (it is the
  owner, sitting at this computer). After that, new accounts need "allow sign-up" in 设置 + an email code.
- Locked out with no email: delete <workspace>/auth/users.json and the app asks for a new first account.

Files: <workspace>/auth/users.json, sessions.json (atomic writes, see store.py).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from .i18n import tr
from .keystore import find_secret, save_secret
from .store import atomic_write_json, read_json

COOKIE = "lacuna_session"
REMEMBER_S = 30 * 86400
SHORT_S = 12 * 3600
CODE_S = 600
CODE_TRIES = 5
CODE_COOLDOWN_S = 60
LOGIN_TRIES = 5
LOCK_S = 60
MIN_PASSWORD = 10
RESEND_KEY = "RESEND_API_KEY"
DEFAULT_SENDER = "LACUNA <onboarding@resend.dev>"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SCRYPT = dict(n=2 ** 14, r=8, p=1, maxmem=64 * 1024 * 1024, dklen=32)


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

    def send(self, sender: str, to: str, subject: str, text: str) -> None:
        key = self._key()
        if not key:
            raise MailError(tr("还没接上 Resend：先在「设置 → 账号与邮件」里填 Resend API key"))
        body = json.dumps({"from": sender, "to": [to], "subject": subject, "text": text}).encode()
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
    def __init__(self, root: Path, mailer=None, clock: Callable[[], float] = time.time, skip_setup: bool = False):
        self.dir = Path(root) / "auth"
        self.skip_setup = skip_setup     # E2E servers: don't force the first-account screen
        self.mailer = mailer if mailer is not None else ResendMailer()
        self.now = clock
        self.lock = threading.Lock()
        data = read_json(self.dir / "users.json") if (self.dir / "users.json").exists() else None
        data = data or {}
        self.users: dict[str, dict] = {u["email"]: u for u in data.get("users", [])}
        self.config: dict = {"allow_register": False, "sender": DEFAULT_SENDER, **data.get("config", {})}
        sess = read_json(self.dir / "sessions.json") if (self.dir / "sessions.json").exists() else None
        now = self.now()
        self.sessions: dict[str, dict] = {k: v for k, v in (sess or {}).get("sessions", {}).items() if v["exp"] > now}
        self.codes: dict[tuple[str, str], dict] = {}
        self.fails: dict[str, list[float]] = {}

    # -- persistence
    def _save_users(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.dir / "users.json", {"users": list(self.users.values()), "config": self.config})

    def _save_sessions(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.dir / "sessions.json", {"sessions": self.sessions})

    # -- queries
    def has_accounts(self) -> bool:
        return bool(self.users)

    def who(self, token: str | None) -> str | None:
        """The signed-in email for a session cookie, or None."""
        if not token:
            return None
        s = self.sessions.get(_sha(token))
        if not s or s["exp"] <= self.now() or s["email"] not in self.users:
            return None
        return s["email"]

    def status(self, token: str | None) -> dict:
        return {"accounts": self.has_accounts(), "setup": not self.users and not self.skip_setup,
                "email": self.who(token),
                "allow_register": bool(self.config["allow_register"]) or not self.users,
                "first": not self.users, "mail": self.mail_status()}

    def mail_status(self) -> dict:
        source = find_secret(RESEND_KEY)[1] if isinstance(self.mailer, ResendMailer) else "test"
        configured = self.mailer.configured()
        return {"configured": configured, "source": source if configured else None, "sender": self.config["sender"]}

    # -- sessions
    def _session(self, email: str, remember: bool) -> tuple[str, int | None]:
        token = secrets.token_urlsafe(32)
        ttl = REMEMBER_S if remember else SHORT_S
        with self.lock:
            now = self.now()
            self.sessions = {k: v for k, v in self.sessions.items() if v["exp"] > now}
            self.sessions[_sha(token)] = {"email": email, "exp": now + ttl, "created": now}
            self._save_sessions()
        return token, (ttl if remember else None)

    def logout(self, token: str | None) -> None:
        with self.lock:
            if token and self.sessions.pop(_sha(token), None) is not None:
                self._save_sessions()

    # -- codes
    def send_code(self, email: str, purpose: str) -> None:
        email = norm_email(email)
        if purpose == "register":
            self._can_register(email)
        elif purpose == "reset":
            if email not in self.users:
                return       # say nothing about which emails have accounts
        else:
            raise AuthError("bad purpose")
        now = self.now()
        old = self.codes.get((email, purpose))
        if old and now - old["sent"] < CODE_COOLDOWN_S:
            raise AuthError(tr("验证码刚发过，{n} 秒后再试", n=int(CODE_COOLDOWN_S - (now - old["sent"])) + 1), 429)
        code = f"{secrets.randbelow(10 ** 6):06d}"
        what = tr("注册 LACUNA 账号") if purpose == "register" else tr("重设 LACUNA 密码")
        try:
            self.mailer.send(self.config["sender"], email, tr("LACUNA 验证码：{code}", code=code),
                             tr("你的验证码是 {code}，10 分钟内有效，用于{what}。\n\n如果不是你本人操作，忽略这封邮件即可。",
                                code=code, what=what))
        except MailError as e:
            raise AuthError(str(e), 502)
        self.codes[(email, purpose)] = {"hash": _sha(code), "exp": now + CODE_S, "tries": 0, "sent": now}

    def _use_code(self, email: str, purpose: str, code: str) -> None:
        c = self.codes.get((email, purpose))
        if not c or c["exp"] <= self.now():
            raise AuthError(tr("验证码过期了，重新发一个"))
        c["tries"] += 1
        if not hmac.compare_digest(c["hash"], _sha((code or "").strip())):
            if c["tries"] >= CODE_TRIES:
                del self.codes[(email, purpose)]
                raise AuthError(tr("验证码错了太多次，重新发一个"))
            raise AuthError(tr("验证码不对"))
        del self.codes[(email, purpose)]

    # -- accounts
    def _can_register(self, email: str) -> None:
        if email in self.users:
            raise AuthError(tr("这个邮箱已经注册过了，直接登录或者找回密码"), 409)
        if self.users and not self.config["allow_register"]:
            raise AuthError(tr("注册已关闭。请账号主人在「设置 → 账号与邮件」里打开「允许新注册」。"), 403)

    def register(self, email: str, password: str, code: str | None, remember: bool) -> tuple[str, int | None]:
        email = norm_email(email)
        check_password(password)
        first = not self.users
        self._can_register(email)
        if not first:
            self._use_code(email, "register", code or "")
        with self.lock:
            self.users[email] = {"email": email, "hash": hash_password(password), "created": self.now(),
                                 "owner": first, "verified": not first}
            self._save_users()
        return self._session(email, remember)

    def login(self, email: str, password: str, remember: bool) -> tuple[str, int | None]:
        email = (email or "").strip().lower()
        now = self.now()
        recent = [t for t in self.fails.get(email, []) if now - t < LOCK_S]
        if len(recent) >= LOGIN_TRIES:
            raise AuthError(tr("密码错了太多次，{n} 秒后再试", n=int(LOCK_S - (now - recent[0])) + 1), 429)
        u = self.users.get(email)
        if not u or not verify_password(password or "", u["hash"]):
            self.fails[email] = recent + [now]
            raise AuthError(tr("邮箱或密码不对"), 401)
        self.fails.pop(email, None)
        return self._session(email, remember)

    def reset(self, email: str, code: str, password: str) -> tuple[str, int | None]:
        email = norm_email(email)
        check_password(password)
        if email not in self.users:
            raise AuthError(tr("验证码过期了，重新发一个"))
        self._use_code(email, "reset", code)
        with self.lock:
            self.users[email]["hash"] = hash_password(password)
            self.users[email]["verified"] = True
            # every other session of this account ends
            self.sessions = {k: v for k, v in self.sessions.items() if v["email"] != email}
            self._save_users()
            self._save_sessions()
        self.fails.pop(email, None)
        return self._session(email, remember=True)

    # -- settings (signed in)
    def update_config(self, allow_register: bool | None = None, sender: str | None = None) -> None:
        with self.lock:
            if allow_register is not None:
                self.config["allow_register"] = bool(allow_register)
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
