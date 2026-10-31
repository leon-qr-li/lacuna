"""Episode naming per album (专辑设置 → 剧集命名, Leon 2026-10-31).

An album may say how its episodes are named: a preset (编号 + 空格 + 名称 is Leon's own) or a custom
one where the user types what goes before the number, between number and name, and after the name.
The format is applied when an episode is imported into the album (the title typed in the import form
is the 名称), and on request to the episodes already in it (「把已有的剧集也改名」). Nothing else
renames an episode, so an album without a format, or one whose format changes, leaves every existing
title as it is.

Stored in albums.json on the album: ``"naming": {"preset", "before", "between", "after"}`` or absent.
"""
from __future__ import annotations

import re

from .i18n import tr

# preset -> (before, between, after); "{n}" in `before` is the episode's number without "EP" and zeros
PRESETS: dict[str, tuple[str, str, str]] = {
    "space": ("", " ", ""),          # EP012 盗梦空间 (Leon's)
    "dot": ("", " · ", ""),          # EP012 · 盗梦空间
    "bar": ("", "｜", ""),            # EP012｜盗梦空间
    "colon": ("", "：", ""),          # EP012：盗梦空间
    "issue": ("第{n}期", " ", ""),     # 第12期 盗梦空间 (the number written the Chinese way)  # i18n-ignore
    "name": ("", "", ""),             # 盗梦空间 (no number)
}
DEFAULT = "space"
MAX_PART = 12
# what can sit between a number and a name in a title typed by hand (stripped to find the bare name)
_SEPS = r"[\s·・|｜:：\-–—_.,，、/]*"


class NamingError(ValueError):
    pass


def clean(naming: dict | None) -> dict | None:
    """A naming from a form, checked; None = no format (titles as typed)."""
    if not naming or not naming.get("preset"):
        return None
    preset = str(naming["preset"])
    if preset == "custom":
        parts = {k: str(naming.get(k) or "")[:MAX_PART] for k in ("before", "between", "after")}
        if any("\n" in v or "\r" in v for v in parts.values()):
            raise NamingError(tr("命名格式里不能换行"))
        return {"preset": "custom", **parts}
    if preset not in PRESETS:
        raise NamingError(tr("没有这种命名格式"))
    return {"preset": preset}


def parts(naming: dict) -> tuple[str, str, str]:
    if naming["preset"] == "custom":
        return naming.get("before", ""), naming.get("between", ""), naming.get("after", "")
    return PRESETS[naming["preset"]]


def number(episode_id: str) -> str:
    """EP012 -> "12" (第{n}期); an id without digits is used as it is."""
    m = re.search(r"(\d+)", episode_id)
    return str(int(m.group(1))) if m else episode_id


def bare(episode_id: str, title: str, naming: dict | None = None) -> str:
    """The 名称 in a title: the episode id (or 第N期) and the separators after it taken off, and the album's
    own before / after text. "EP012 · 盗梦空间" -> "盗梦空间"; a title that is only the id -> ""."""
    s = " ".join((title or "").split())
    if naming:
        before, _, after = parts(naming)
        b = before.replace("{n}", number(episode_id))
        if b and s.startswith(b):
            s = s[len(b):]
        if after and s.endswith(after):
            s = s[: -len(after)]
    s = re.sub(rf"^{re.escape(episode_id)}{_SEPS}", "", s, flags=re.I)
    s = re.sub(rf"^第\s*0*{re.escape(number(episode_id))}\s*[期集]{_SEPS}", "", s)  # i18n-ignore
    if naming and naming["preset"] == "custom":
        between = naming.get("between", "")
        if between and s.startswith(between):
            s = s[len(between):]
    return s.strip()


def title(naming: dict | None, episode_id: str, name: str) -> str:
    """The episode's title under the album's format. No format: the name typed (or the id when empty)."""
    name = " ".join((name or "").split())
    if not naming:
        return name or episode_id
    before, between, after = parts(naming)
    before = before.replace("{n}", number(episode_id))
    if naming["preset"] == "name":
        return name or episode_id
    num = before if "{n}" in parts(naming)[0] else before + episode_id
    if not name:
        return (num + after).strip() or episode_id
    return (num + between + name + after).strip()
