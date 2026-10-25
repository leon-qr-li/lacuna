"""用户条款和隐私政策 (decision 2026-10-25-terms-and-privacy): which version is current and who agreed to it.

The documents themselves are web pages (web/src/features/legal/docs/<terms|privacy>.<zh|en>.md), readable without
signing in at /legal/terms and /legal/privacy. Each account keeps the version it agreed to and when
(`users[email]["terms"] = {"v": VERSION, "at": <unix time>}`). In the cloud, creating an account needs the box
ticked, and someone whose agreed version is older than VERSION sees the 「条款已更新」 screen before the app opens.

Bump VERSION (a date) whenever the text changes in a way people must agree to again (the lawyer's version, a new
company entity); a typo fix doesn't need it. tests/app/test_legal.py checks every document names VERSION.
"""
from __future__ import annotations

VERSION = "2026-10-25"


def record(version: str | None, now: float) -> dict:
    """The fields a new or existing account stores when it agrees (empty when it didn't)."""
    return {"terms": {"v": version, "at": now}} if version == VERSION else {}


def agreed(user: dict | None) -> str | None:
    """The version this account agreed to, or None."""
    return ((user or {}).get("terms") or {}).get("v")


def current(user: dict | None) -> bool:
    return agreed(user) == VERSION
