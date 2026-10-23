"""上传喜马拉雅 (phase 11): everything Leon needs to upload one episode by hand, in the order of the
喜马拉雅 upload form. 喜马拉雅 has no upload API for personal creators, so the App only prepares
(docs/decisions/2026-10-17-ximalaya-no-upload-api.md).

Nothing new is produced here: the WAV comes from the export (D36), title / blurb / show notes from the
publish pack (phase 9), the cover from phase 10. This module finds the newest of each and says what is
missing or out of date.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from .episode import Episode
from .store import read_json

UPLOAD_PAGE = "https://studio.ximalaya.com/"


def latest_wav(exports_dir: Path) -> tuple[Path, dict] | None:
    """Newest exported WAV and its sidecar record (``<basename>.json``, may be missing)."""
    if not exports_dir.is_dir():
        return None
    wavs = [p for p in exports_dir.iterdir() if p.is_file() and p.suffix.lower() == ".wav"]
    if not wavs:
        return None
    wav = max(wavs, key=lambda p: (p.stat().st_mtime, p.name))
    side = wav.with_suffix(".json")
    try:
        record = read_json(side) if side.is_file() else {}
    except (OSError, ValueError):
        record = {}
    return wav, record


def checklist(ep: Episode, exports_dir: Path, publish_view: dict, poster_doc: dict,
              music_version: str | None = None) -> dict:
    """What is ready for the upload form. ``publish_view`` is ``Publisher.view``; ``poster_doc`` is
    ``Posters.load``."""
    version = ep.version_key()
    audio = None
    found = latest_wav(exports_dir)
    if found:
        wav, record = found
        audio = {"name": wav.name, "bytes": wav.stat().st_size,
                 "exported_at": record.get("exported_at"),
                 # an export without a record is from before records existed: we can't tell, so not stale
                 "stale": (bool(record.get("version")) and record["version"] != version)
                 or (bool(record.get("music_version")) and music_version is not None
                     and record["music_version"] != music_version)}

    pack = publish_view.get("pack")
    cover = poster_doc.get("cover")
    if cover and not Path(cover["jpg"]).is_file():
        cover = None
    return {
        "upload_page": UPLOAD_PAGE,
        "audio": audio,
        "pack": {"stale": pack["stale"], "edited": pack["edited"]} if pack else None,
        "cover": {"bytes": cover["jpg_bytes"], "px": cover["px"], "rendered_at": cover["rendered_at"]} if cover else None,
        "ready": bool(audio and not audio["stale"] and pack and not pack["stale"] and cover),
    }


def cover_path(poster_doc: dict, cover_dir: Path) -> Path:
    """The chosen cover JPEG, only from the episode's own publish folder."""
    cover = poster_doc.get("cover")
    if not cover:
        raise FileNotFoundError("no cover chosen")
    p = Path(cover["jpg"])
    if p.resolve().parent != cover_dir.resolve() or not p.is_file():
        raise FileNotFoundError(str(p))
    return p


def save_cover(cover_jpg: Path, exports_dir: Path, episode_id: str) -> Path:
    """Copy the chosen cover next to the exported WAV / MP3 (``exports/<ep>/<ep>_cover.jpg``), so the
    folder Leon uploads from has everything; the publish/ copy stays where it is."""
    exports_dir.mkdir(parents=True, exist_ok=True)
    out = exports_dir / f"{episode_id}_cover.jpg"
    tmp = out.with_name(out.name + ".tmp")
    shutil.copyfile(cover_jpg, tmp)
    tmp.replace(out)
    return out
