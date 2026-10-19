"""The show a workspace makes: its name, hosts (one track each) and how LACUNA edits and presents it.

Until 2026-10-19 all of this was written into the code for 《洛城二三事》 (Leon + Pei). Now each
workspace keeps its own profile in ``<workspace>/show.json`` (atomic write + .bak, store.py), next to
its episodes, library and learned rules; the profile is a separate object so it can later be shared
or copied on its own. Decision: docs/decisions/2026-10-19-show-profile.md.

A workspace without the file:
* the installation's own folder ("main") or any folder that already has episodes is Leon's show,
  so ``LEGACY`` (exactly what the code did before) applies and nothing changes for him;
* any other workspace (``<root>/spaces/sp_…``, empty) is new: ``needs_setup`` is true and the app
  asks for the show name and hosts first (Spaces.create also writes such a file).

Hosts carry a one-letter ``tag`` (track id inside an import: token ids are ``<tag>000123``) and a
``name`` (the episode's track name, shown everywhere). Tags never change once given, so a renamed
host keeps their imports and learned habits apart from everyone else's.
"""
from __future__ import annotations

import copy
import string
from pathlib import Path

from .i18n import tr
from .store import atomic_write_json, read_json

FILE = "show.json"
VERSION = 1
MAX_HOSTS = 6
# colour names, each a light + dark pair in web/src/features/show/show.css (WCAG AA checked there)
COLORS = ("blue", "purple", "teal", "amber", "green", "pink")
CUT_LEVELS = ("gentle", "normal", "firm")
# letters for new hosts' tags; I/O look like digits
_TAGS = [c for c in string.ascii_uppercase if c not in "IOLP"]
# (L and P: Leon and Pei in LEGACY)

LEGACY: dict = {
    "version": VERSION,
    "setup_done": True,
    "legacy": True,          # Leon's show: the EP001-calibrated prompts and texts, unchanged
    "show_name": "洛城二三事",  # i18n-ignore
    "about": "两个朋友的电影闲聊",  # i18n-ignore
    "hosts": [
        {"tag": "L", "name": "Leon", "color": "blue", "cut_level": "firm",
         "style": "Cut his rambling hard: tangents, restarts, long build-ups."},
        {"tag": "P", "name": "Pei", "color": "purple", "cut_level": "normal",
         "style": "Somewhat strict with her clear stumbles, but gentler than with Leon; keep some of her tics."},
    ],
    "footer": "*《洛城二三事》是 Leon 和 Pei 两个人的电影闲聊。觉得好听，就分享给一个也爱看电影的朋友吧。*",  # i18n-ignore
    "publish": {"ximalaya": True, "album": "洛城二三事"},  # i18n-ignore
}

NEW: dict = {
    "version": VERSION,
    "setup_done": False,
    "legacy": False,
    "show_name": "",
    "about": "",
    "hosts": [],
    "footer": "",
    "publish": {"ximalaya": False, "album": ""},
}


class ShowError(ValueError):
    """A profile the user has to fix (message in the interface language)."""


def _is_new_space(root: Path) -> bool:
    """An extra workspace (spaces.py puts them at <root>/spaces/sp_…) that has no episodes yet."""
    if not (root.parent.name == "spaces" and root.name.startswith("sp_")):
        return False
    eps = root / "episodes"
    return not (eps.is_dir() and any(p.is_dir() and not p.name.startswith(".") for p in eps.iterdir()))


def load(root: str | Path) -> dict:
    """The workspace's profile, normalised (see the module docstring for a missing file)."""
    root = Path(root)
    f = root / FILE
    if f.is_file() or f.with_name(FILE + ".bak").is_file():
        try:
            return normalise(read_json(f), strict=False)
        except (OSError, ValueError):
            pass
    return copy.deepcopy(NEW if _is_new_space(root) else LEGACY)


def save(root: str | Path, data: dict) -> dict:
    """Validate and store `data` (a full profile from the 节目设置 page); returns what was stored."""
    root = Path(root)
    before = load(root)
    clean = normalise(data, strict=True, before=before)
    clean["setup_done"] = True
    atomic_write_json(root / FILE, clean)
    return clean


def write_new(root: str | Path) -> None:
    """A workspace just created: no show yet, so the first visit asks for one."""
    root = Path(root)
    if not (root / FILE).exists():
        atomic_write_json(root / FILE, copy.deepcopy(NEW))


def _text(v, limit: int) -> str:
    return " ".join(str(v or "").split())[:limit]


def normalise(data: dict, strict: bool, before: dict | None = None) -> dict:
    """A clean profile from `data`: unknown keys dropped, lengths capped, colours and levels from the
    allowed sets, every host with a unique tag. `strict` (saving) refuses what would break imports."""
    data = data if isinstance(data, dict) else {}
    legacy = bool((before or data).get("legacy"))
    out = {"version": VERSION, "setup_done": bool(data.get("setup_done", True)), "legacy": legacy,
           "show_name": _text(data.get("show_name"), 80), "about": _text(data.get("about"), 200),
           "footer": str(data.get("footer") or "").strip()[:600]}
    pub = data.get("publish") if isinstance(data.get("publish"), dict) else {}
    out["publish"] = {"ximalaya": bool(pub.get("ximalaya")), "album": _text(pub.get("album"), 80)}

    old_tags = {h["tag"]: h for h in (before or {}).get("hosts", [])}
    hosts, used_tags, used_names = [], set(), set()
    for i, h in enumerate(data.get("hosts") or []):
        if not isinstance(h, dict):
            continue
        name = _text(h.get("name"), 40)
        if not name:
            if strict:
                raise ShowError(tr("第 {n} 位主持人还没有名字", n=i + 1))
            continue
        if name.lower() in used_names:
            if strict:
                raise ShowError(tr("两位主持人不能同名：{name}", name=name))
            continue
        tag = str(h.get("tag") or "")
        # a tag stays with its host; on save only tags this workspace already gave out are kept
        if not (len(tag) == 1 and tag in _TAGS + ["L", "P"] and tag not in used_tags
                and (before is None or tag in old_tags)):
            tag = ""
        color = h.get("color") if h.get("color") in COLORS else COLORS[len(hosts) % len(COLORS)]
        level = h.get("cut_level") if h.get("cut_level") in CUT_LEVELS else "normal"
        hosts.append({"tag": tag, "name": name, "color": color, "cut_level": level,
                      "style": str(h.get("style") or "").strip()[:500]})
        used_tags.add(tag)
        used_names.add(name.lower())
    taken = {h["tag"] for h in hosts if h["tag"]} | set(old_tags)
    free = (t for t in _TAGS if t not in taken)
    for h in hosts:
        if not h["tag"]:
            h["tag"] = next(free)
    if strict:
        if not out["show_name"]:
            raise ShowError(tr("给节目起个名字"))
        if not hosts:
            raise ShowError(tr("至少要有一位主持人"))
        if len(hosts) > MAX_HOSTS:
            raise ShowError(tr("最多 {n} 位主持人", n=MAX_HOSTS))
    out["hosts"] = hosts[:MAX_HOSTS]
    return out


# ---------------------------------------------------------------------------- helpers for other modules

def view(profile: dict) -> dict:
    """What the interface gets (GET /api/show)."""
    return profile | {"needs_setup": not profile.get("setup_done"), "colors": list(COLORS),
                      "cut_levels": list(CUT_LEVELS), "max_hosts": MAX_HOSTS}


def tracks(profile: dict) -> list[tuple[str, str]]:
    """[(tag, track name)] in host order: the tracks a new import asks for."""
    return [(h["tag"], h["name"]) for h in profile["hosts"]]


def host_names(profile: dict) -> list[str]:
    return [h["name"] for h in profile["hosts"]]


def byline(profile: dict) -> str:
    """"Leon & Pei", "A, B & C", or one name."""
    names = host_names(profile)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " & " + names[-1] if names else ""
