"""Build a LACUNA release (phase 7, D50): the app zip with the built UI, its feed and the installers.

    python installer/build_release.py --version 2026.10.17.1 --out dist [--notes "…"] [--url-base URL]

Needs `web/dist` (npm run build). Writes into --out:
    lacuna.zip            code (lacuna_core, lacuna_app, scripts, installer), built UI, pyproject, VERSION
    version.json          {"schema", "version", "notes", "zip", "sha256", "size", "published"}
    lacuna_launcher.py, install.sh, install.ps1, LACUNA-Setup.cmd

`zip` in version.json is `<url-base>/lacuna.zip` when --url-base is given (GitHub: the tag's own
download folder, so a client that read the feed downloads exactly that version), else the bare name,
resolved next to version.json (local folders in tests).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INCLUDE_DIRS = ["lacuna_core", "lacuna_app", "scripts", "installer"]
INCLUDE_FILES = ["pyproject.toml", "README.md"]
INSTALLERS = ["lacuna_launcher.py", "install.sh", "install.ps1", "LACUNA-Setup.cmd"]
SKIP = {"__pycache__", ".pytest_cache"}


def files_to_ship(repo: Path) -> list[tuple[Path, str]]:
    out: list[tuple[Path, str]] = []
    for d in INCLUDE_DIRS:
        for p in sorted((repo / d).rglob("*")):
            if p.is_file() and not SKIP.intersection(p.relative_to(repo).parts) and p.suffix != ".pyc":
                out.append((p, p.relative_to(repo).as_posix()))
    dist = repo / "web" / "dist"
    if not (dist / "index.html").is_file():
        raise SystemExit("web/dist/index.html missing: run `npm ci && npm run build` in web/ first")
    for p in sorted(dist.rglob("*")):
        if p.is_file():
            out.append((p, p.relative_to(repo).as_posix()))
    for f in INCLUDE_FILES:
        out.append((repo / f, f))
    return out


def build(version: str, out: Path, notes: str = "", url_base: str | None = None, repo: Path = REPO) -> dict:
    if not all(x.isdigit() for x in version.split(".")):
        raise SystemExit(f"version must be dotted numbers, got {version!r}")
    out.mkdir(parents=True, exist_ok=True)
    zpath = out / "lacuna.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("VERSION", version + "\n")
        for src, arc in files_to_ship(repo):
            z.write(src, arc)
    data = zpath.read_bytes()
    feed = {"schema": 1, "version": version, "notes": notes.strip(),
            "zip": f"{url_base.rstrip('/')}/lacuna.zip" if url_base else "lacuna.zip",
            "sha256": hashlib.sha256(data).hexdigest(), "size": len(data),
            "published": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    (out / "version.json").write_text(json.dumps(feed, ensure_ascii=False, indent=2), encoding="utf-8")
    for name in INSTALLERS:
        shutil.copyfile(repo / "installer" / name, out / name)
    return feed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--notes", default="")
    ap.add_argument("--notes-file", type=Path)
    ap.add_argument("--url-base")
    a = ap.parse_args(argv)
    notes = a.notes_file.read_text(encoding="utf-8") if a.notes_file else a.notes
    feed = build(a.version, a.out, notes, a.url_base)
    print(json.dumps(feed, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
