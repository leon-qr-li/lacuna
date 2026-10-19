"""Two-step sign-in codes from an authenticator app (RFC 6238 TOTP: SHA-1, 30 s, 6 digits).

Works with Google Authenticator, Microsoft Authenticator, 1Password, iOS Passwords and the like.
No dependency: the algorithm is a few lines of hmac.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
from urllib.parse import quote

STEP = 30
DIGITS = 6
WINDOW = 1          # also accept the code from one step before / after (phone clock drift)


def new_secret() -> str:
    """160 random bits, base32 without padding (what authenticator apps expect)."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _key(secret: str) -> bytes:
    s = secret.strip().replace(" ", "").upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def code_at(secret: str, counter: int) -> str:
    mac = hmac.new(_key(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    n = struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF
    return f"{n % 10 ** DIGITS:0{DIGITS}d}"


def match(secret: str, code: str, now: float, after: int = -1) -> int | None:
    """The time step `code` belongs to (within the window), or None. Steps at or before `after`
    (the last one used) are refused, so a code can't be replayed."""
    code = (code or "").strip().replace(" ", "")
    if len(code) != DIGITS or not code.isdigit():
        return None
    t = int(now // STEP)
    for c in range(t - WINDOW, t + WINDOW + 1):
        if c > after and hmac.compare_digest(code_at(secret, c), code):
            return c
    return None


def uri(secret: str, account: str, issuer: str = "LACUNA") -> str:
    """otpauth:// link, shown as a QR code for the authenticator app to scan."""
    return (f"otpauth://totp/{quote(issuer)}:{quote(account)}?secret={secret}&issuer={quote(issuer)}"
            f"&algorithm=SHA1&digits={DIGITS}&period={STEP}")


def recovery_codes(n: int = 10) -> list[str]:
    """One-time codes for a lost phone: 10 characters in two groups, no look-alike letters."""
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return ["-".join("".join(secrets.choice(alphabet) for _ in range(5)) for _ in range(2)) for _ in range(n)]


def norm_recovery(code: str) -> str:
    c = "".join(ch for ch in (code or "").lower() if ch.isalnum())
    return f"{c[:5]}-{c[5:]}" if len(c) == 10 else ""
