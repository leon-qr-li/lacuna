"""Secrets other than the Claude key (e.g. RESEND_API_KEY), stored like the Claude key is (editor.py):
Windows = user environment in the registry (what `setx` writes), macOS = login Keychain, elsewhere = a
0600 file under LACUNA_HOME (or ~/.config/lacuna). The process environment wins over all of them.
Never log a secret."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

KEYCHAIN_SERVICE = "LACUNA"


def _file(name: str) -> Path:
    home = os.environ.get("LACUNA_HOME")
    return (Path(home) if home else Path.home() / ".config" / "lacuna") / name.lower()


def find_secret(name: str) -> tuple[str | None, str]:
    """(value, where it came from) or (None, "missing")."""
    v = (os.environ.get(name) or "").strip().strip('"')
    if v:
        return v, "env"
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                v = str(winreg.QueryValueEx(k, name)[0] or "").strip().strip('"')
        except OSError:
            v = ""
        if v:
            return v, "registry-user"
    elif sys.platform == "darwin":
        try:
            out = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", name, "-w"],
                                 capture_output=True, text=True, timeout=10)
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.strip(), "keychain"
        except (OSError, subprocess.TimeoutExpired):
            pass
    try:
        v = _file(name).read_text(encoding="utf-8").strip()
    except OSError:
        v = ""
    return (v, "file") if v else (None, "missing")


def save_secret(name: str, value: str) -> str:
    """Store `value` where `find_secret` looks on this OS; returns where."""
    if sys.platform == "win32":
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
        where = "registry-user"
    elif sys.platform == "darwin":
        out = subprocess.run(["security", "add-generic-password", "-U", "-s", KEYCHAIN_SERVICE, "-a", name, "-w", value],
                             capture_output=True, text=True, timeout=20)
        if out.returncode != 0:
            raise OSError(out.stderr.strip())
        where = "keychain"
    else:
        f = _file(name)
        f.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(value)
        where = "file"
    os.environ.pop(name, None)   # a stale value in this process must not shadow the new one
    return where
