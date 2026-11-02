"""An episode's name (Leon 2026-11-02, decision `2026-11-02-episode-naming`).

The name is typed at import, picked from LACUNA's titles on the publish page, or changed any time from the
episode page or the home card. It is stored as the episode's title (``episode.json``); in an album with a
naming format (naming.py) the user only gives the 名称 part and the format adds the number around it.

An episode nobody has named yet has a title that is only its number (``EP012``, or the album format with
an empty 名称): the home card says 还没起名 and the publish page asks for a pick.
"""
from __future__ import annotations

from . import naming
from .albums import Albums
from .episode import Episode


def album_format(ws, episode_id: str) -> tuple[dict | None, dict | None]:
    """(album, its naming format) of the episode; (None, None) outside an album."""
    try:
        a = Albums(ws)
        aid = a.album_of(episode_id)
        album = next((x for x in a.albums() if x["id"] == aid), None) if aid else None
    except (OSError, ValueError):
        album = None
    return album, (album or {}).get("naming")


def name_of(episode_id: str, title: str, fmt: dict | None) -> str:
    """The part of the title the user named ("" = not named yet). Without a format that is the whole title."""
    title = " ".join((title or "").split())
    if fmt:
        return naming.bare(episode_id, title, fmt)
    return "" if title in ("", episode_id) else title


def view(ws, ep: Episode) -> dict:
    album, fmt = album_format(ws, ep.id)
    title = str(ep.meta.get("title") or ep.id)
    name = name_of(ep.id, title, fmt)
    return {"id": ep.id, "title": title, "name": name, "named": bool(name),
            # the name without the episode number: what the publish pack's title is
            "short": naming.bare(ep.id, title, fmt) if name else "",
            "album": {"id": album["id"], "name": album.get("name", "")} if album else None,
            "naming": fmt}


def rename(ws, ep: Episode, name: str) -> dict:
    """Give the episode this name ("" = back to only its number). Returns the new view."""
    _, fmt = album_format(ws, ep.id)
    name = " ".join((name or "").split())
    ep.set_title(naming.title(fmt, ep.id, name))
    return view(ws, ep)
