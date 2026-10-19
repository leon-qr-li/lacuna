"""Moving the desktop workspace to the shared server (decision cloud-deploy).

In 设置 on lacunastudio.app the owner picks the desktop's LACUNA_Workspace folder; the browser sends
every file (big ones in pieces, upload_parts.py) into ``<workspace>/tmp/migrate/files/<path>``. Sending
again skips files already there with the same size, so a dropped connection just resumes. "Finish"
checks the file count and bytes against what the browser counted, then moves the files into the main
workspace, rewriting the desktop's absolute paths in JSON (an episode's media lives at
``C:\\Projects\\LACUNA_Workspace\\episodes\\…`` on the desktop) to the server's folder, and the app
restarts to load it all. The desktop folder is only read; nothing there changes.

Never copied: ``auth/`` and ``spaces/`` (the server's own accounts and workspaces), ``models/`` (the
server downloads its own), ``tmp/``.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path, PurePosixPath

from .store import Workspace

SKIP_TOP = {"auth", "spaces", "models", "tmp"}
SKIP_NAMES = {"desktop.ini", "Thumbs.db", ".DS_Store"}
MAX_PATH = 400
_BAD = re.compile(r'[\x00-\x1f\\:*?"<>|]')
# an absolute desktop path into the workspace: <old root>/episodes/… or <old root>/library/…
_INSIDE = re.compile(r"^(?P<root>(?:[A-Za-z]:|/|\\\\).*?)[\\/](?:episodes|library)[\\/][^\\/].*$")


class MigrateError(ValueError):
    pass


class NotAWorkspace(MigrateError):
    pass


def staging(ws: Workspace) -> Path:
    return ws.root / "tmp" / "migrate" / "files"


def clean_path(rel: str) -> str | None:
    """`rel` as a safe relative posix path, or None for a file that is never copied."""
    rel = (rel or "").replace("\\", "/").strip("/")
    parts = PurePosixPath(rel).parts
    if not parts or len(rel) > MAX_PATH:
        raise MigrateError("bad path")
    for p in parts:
        if p in ("", ".", "..") or _BAD.search(p) or p != p.strip():
            raise MigrateError("bad path")
    if parts[0] in SKIP_TOP or parts[-1] in SKIP_NAMES:
        return None
    return "/".join(parts)


def staged(ws: Workspace) -> dict[str, int]:
    root = staging(ws)
    if not root.is_dir():
        return {}
    return {p.relative_to(root).as_posix(): p.stat().st_size for p in root.rglob("*")
            if p.is_file() and not p.name.endswith(".uploading")}


def target(ws: Workspace, rel: str) -> Path:
    p = staging(ws) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def cancel(ws: Workspace) -> None:
    shutil.rmtree(ws.root / "tmp" / "migrate", ignore_errors=True)


def _is_json(name: str) -> bool:
    return name.endswith(".json") or name.endswith(".json.bak")


def old_roots(files: dict[str, int], root: Path) -> list[str]:
    """The desktop workspace's absolute path(s), read off the paths saved in its JSON files."""
    found: set[str] = set()
    for rel in files:
        if not _is_json(rel):
            continue
        try:
            data = json.loads((root / rel).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for s in _strings(data):
            m = _INSIDE.match(s)
            if m and not s.startswith(str(root)):
                found.add(m.group("root"))
    return sorted(found, key=len, reverse=True)


def _strings(data):
    if isinstance(data, str):
        yield data
    elif isinstance(data, dict):
        for v in data.values():
            yield from _strings(v)
    elif isinstance(data, list):
        for v in data:
            yield from _strings(v)


def remap(data, roots: list[str], new_root: Path):
    """Every string under one of the desktop `roots` now points under `new_root`."""
    if isinstance(data, str):
        for r in roots:
            if data == r or (data.lower().startswith(r.lower()) and data[len(r)] in "\\/"):
                rest = data[len(r):].replace("\\", "/").lstrip("/")
                return str(new_root / rest) if rest else str(new_root)
        return data
    if isinstance(data, dict):
        return {k: remap(v, roots, new_root) for k, v in data.items()}
    if isinstance(data, list):
        return [remap(v, roots, new_root) for v in data]
    return data


def finish(ws: Workspace, files: int, size: int) -> dict:
    """Check what arrived against the browser's count, then move it into the workspace."""
    root = staging(ws)
    have = staged(ws)
    if len(have) != files or sum(have.values()) != size:
        raise MigrateError(f"expected {files} files / {size} bytes, have {len(have)} / {sum(have.values())}")
    if not any(r.startswith("episodes/") for r in have) and not any(r.startswith("library/") for r in have):
        raise NotAWorkspace("no episodes or library in this folder")
    roots = old_roots(have, root)
    rewritten = 0
    if roots:
        for rel in have:
            if not _is_json(rel):
                continue
            p = root / rel
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            new = remap(data, roots, ws.root)
            if new != data:
                p.write_text(json.dumps(new, ensure_ascii=False, indent=1), encoding="utf-8")
                rewritten += 1
    for rel in have:
        dst = ws.root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.replace(root / rel, dst)
    cancel(ws)
    return {"files": len(have), "bytes": sum(have.values()), "rewritten": rewritten,
            "episodes": len({r.split("/")[1] for r in have if r.startswith("episodes/") and r.count("/") >= 2})}
