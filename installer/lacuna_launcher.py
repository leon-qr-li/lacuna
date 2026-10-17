"""LACUNA launcher: install, start and update LACUNA Studio without a command line (phase 7, D51).

Standard library only: it runs before any dependency is installed, and it must keep working while
the app version it starts is being replaced. It lives in the install root:

    <root>/bin/uv(.exe)              uv (installs Python and the packages)
    <root>/python/                   Python managed by uv
    <root>/cache/                    uv's download cache (makes a rollback work offline)
    <root>/venv/                     one virtual environment shared by the app versions
    <root>/versions/<version>/       the app (release zip: code + built UI), current + previous kept
    <root>/ffmpeg/                   ffmpeg + ffprobe (static builds, checksums pinned below)
    <root>/config.json               workspace, port, current / previous version
    <root>/pending.json              written by the app: "switch to this prepared version"
    <root>/update_log.json           what the last update did (the app shows it)
    <root>/LACUNA.cmd | LACUNA.command   what the desktop shortcut / LACUNA.app starts
    <root>/LACUNA.ico | LACUNA.icns       the shortcut / LACUNA.app icon (copied from the app version)

Roots: Windows %LOCALAPPDATA%\\LACUNA, macOS ~/Library/Application Support/LACUNA,
Linux ~/.local/share/lacuna. The workspace (episodes, models, exports) is elsewhere and is never
touched by install, update or removal of the root.

Commands:
    install   download the latest release (or --zip), set up Python + packages + ffmpeg, write
              config and shortcuts, then start (unless --no-start). Running it again repairs /
              updates an existing install and keeps its workspace.
    run       start the app; restart it when it asks for an update (exit 75) or a plain restart
              (exit 76). After an update the new version must answer /api/app within the health
              timeout, otherwise the previous version is reinstalled and started again.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import webbrowser
import zipfile
from pathlib import Path

APP = "LACUNA"
DEFAULT_BASE = "https://github.com/leon-qr-li/lacuna/releases/latest/download"
FEED_NAME = "version.json"
EXTRAS = "claude,asr"
PYTHON = "3.12"
DEFAULT_PORT = 8765
UPDATE_EXIT = 75      # the app prepared a new version and wants to be swapped
RESTART_EXIT = 76     # the app wants a plain restart (e.g. a new API key was saved)
HEALTH_TIMEOUT = 180.0
CONFIG_SCHEMA = 1

# Static ffmpeg 6.1.1 builds (github.com/eugeneware/ffmpeg-static, release b6.1.1), gzip'd.
FFMPEG_BASE = "https://github.com/eugeneware/ffmpeg-static/releases/download/b6.1.1/"
FFMPEG_SHA256 = {
    "ffmpeg-darwin-arm64.gz": "8923876afa8db5585022d7860ec7e589af192f441c56793971276d450ed3bbfa",
    "ffprobe-darwin-arm64.gz": "d986a8ec7b030899fe66a8a288ed809a3543338705a3ce178cfb85869c5d80be",
    "ffmpeg-darwin-x64.gz": "929b375c1182d956c51f7ac25e0b2b0411fb01f6f407aa15c9758efeb4242106",
    "ffprobe-darwin-x64.gz": "d4da574d6e2e197bd259b47d69cf262df9e312af24ad960444f6d806d3d4c186",
    "ffmpeg-win32-x64.gz": "8883a3dffbd0a16cf4ef95206ea05283f78908dbfb118f73c83f4951dcc06d77",
    "ffprobe-win32-x64.gz": "f309e6223ad89d2fe54bccd420a7709b66fd27540674e92309578ed491a43c8d",
    "ffmpeg-linux-x64.gz": "bfe8a8fc511530457b528c48d77b5737527b504a3797a9bc4866aeca69c2dffa",
    "ffprobe-linux-x64.gz": "25d9b6ccb05e3d9de9e04e31e2506d8dd7f9f0418981965ac6df12e8d3afd067",
}

WINDOWS = sys.platform == "win32"
MACOS = sys.platform == "darwin"


class LauncherError(RuntimeError):
    """Something the person has to read (printed in Chinese, no traceback)."""


def say(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------------------- paths & config

def default_root() -> Path:
    if WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / APP
    if MACOS:
        return Path.home() / "Library" / "Application Support" / APP
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "lacuna"


def default_workspace() -> Path:
    leon = Path(r"C:\Projects\LACUNA_Workspace")      # Leon's existing workspace (since 2026-10-16)
    if WINDOWS and leon.is_dir():
        return leon
    return Path.home() / "LACUNA_Workspace"


def venv_python(root: Path) -> Path:
    return root / "venv" / ("Scripts/python.exe" if WINDOWS else "bin/python")


def uv_path(root: Path) -> Path:
    return root / "bin" / ("uv.exe" if WINDOWS else "uv")


def ffmpeg_dir(root: Path) -> Path:
    return root / "ffmpeg"


def read_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_json(p: Path, data: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def load_config(root: Path) -> dict:
    cfg = read_json(root / "config.json")
    if not cfg:
        raise LauncherError(f"{APP} 还没有装好（{root} 里没有 config.json），请重新运行安装。")
    return cfg


def version_key(v: str) -> tuple:
    """'2026.10.17.2' -> (2026, 10, 17, 2); anything else sorts lowest."""
    try:
        return tuple(int(x) for x in v.split("."))
    except (AttributeError, ValueError):
        return ()


# ---------------------------------------------------------------------------- downloads

def as_url(base: str) -> str:
    """A release base can be a URL or a local folder (CI and offline installs)."""
    if "://" in base:
        return base.rstrip("/")
    return Path(base).resolve().as_uri()


def join_url(base: str, name: str) -> str:
    if "://" in name:
        return name
    return as_url(base) + "/" + urllib.parse.quote(name)


def fetch_bytes(url: str, timeout: float = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": f"{APP}-launcher"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def download(url: str, dst: Path, sha256: str | None = None, label: str = "") -> Path:
    """Stream `url` to `dst` (via .part), printing progress; verify sha256 when given."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    part = dst.with_name(dst.name + ".part")
    h = hashlib.sha256()
    req = urllib.request.Request(url, headers={"User-Agent": f"{APP}-launcher"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done, shown = 0, -10
            while chunk := r.read(1 << 20):
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                pct = int(done * 100 / total) if total else -1
                if label and total and pct >= shown + 10:
                    say(f"  {label} {pct}%")
                    shown = pct
    except OSError as e:
        part.unlink(missing_ok=True)
        raise LauncherError(f"下载失败：{url}\n  {e}\n  检查网络后再试一次。") from e
    if sha256 and h.hexdigest() != sha256.lower():
        part.unlink(missing_ok=True)
        raise LauncherError(f"下载的文件校验不对（{dst.name}），可能没下完整。再试一次。")
    os.replace(part, dst)
    return dst


def read_feed(base: str) -> dict:
    url = join_url(base, FEED_NAME)
    try:
        feed = json.loads(fetch_bytes(url))
    except (OSError, ValueError) as e:
        raise LauncherError(f"读不到最新版本信息：{url}\n  {e}") from e
    if not feed.get("version") or not feed.get("zip") or not feed.get("sha256"):
        raise LauncherError(f"版本信息不完整：{url}")
    return feed


def extract_release(zip_path: Path, versions: Path) -> tuple[str, Path]:
    """Unpack a release zip into versions/<VERSION>/ (atomically, via a temp folder)."""
    with zipfile.ZipFile(zip_path) as z:
        try:
            version = z.read("VERSION").decode().strip()
        except KeyError:
            raise LauncherError(f"{zip_path.name} 不是 {APP} 的发版包（里面没有 VERSION）")
        if not version_key(version):
            raise LauncherError(f"发版包的版本号不对：{version!r}")
        dst = versions / version
        if (dst / "VERSION").is_file():
            return version, dst
        versions.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix=f".{version}-", dir=versions))
        z.extractall(tmp)          # zipfile drops absolute paths and '..' components
    if dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
    os.replace(tmp, dst)
    return version, dst


# ---------------------------------------------------------------------------- uv, packages, ffmpeg

def uv_env(root: Path) -> dict:
    env = dict(os.environ)
    env.update(UV_PYTHON_INSTALL_DIR=str(root / "python"), UV_CACHE_DIR=str(root / "cache"),
               UV_LINK_MODE="copy", UV_NO_PROGRESS="1", PYTHONUTF8="1")
    env.pop("VIRTUAL_ENV", None)
    return env


def run_cmd(cmd: list, env: dict | None = None, cwd: Path | None = None) -> int:
    return subprocess.call([str(c) for c in cmd], env=env, cwd=cwd)


def ensure_venv(root: Path, runner=run_cmd) -> None:
    if venv_python(root).is_file():
        return
    say(f"准备 Python {PYTHON} …")
    if runner([uv_path(root), "venv", "--python", PYTHON, root / "venv"], env=uv_env(root)) != 0:
        raise LauncherError("建 Python 环境失败（uv venv）。")


def install_packages(root: Path, app_dir: Path, runner=run_cmd) -> bool:
    say(f"安装 {APP} 需要的组件（第一次要下载几百 MB，之后很快）…")
    code = runner([uv_path(root), "pip", "install", "--python", venv_python(root),
                   "-e", f"{app_dir}[{EXTRAS}]"], env=uv_env(root))
    return code == 0


def ffmpeg_platform() -> str:
    machine = platform.machine().lower()
    if WINDOWS:
        return "win32-x64"
    if MACOS:
        return "darwin-arm64" if machine in ("arm64", "aarch64") else "darwin-x64"
    if machine in ("x86_64", "amd64"):
        return "linux-x64"
    raise LauncherError(f"这台电脑（{sys.platform} {machine}）没有现成的 ffmpeg，请自己装 ffmpeg。")


def ensure_ffmpeg(root: Path) -> Path:
    d = ffmpeg_dir(root)
    ext = ".exe" if WINDOWS else ""
    plat = ffmpeg_platform()
    for tool in ("ffmpeg", "ffprobe"):
        exe = d / f"{tool}{ext}"
        if exe.is_file():
            continue
        name = f"{tool}-{plat}.gz"
        say(f"下载 {tool} …")
        gz = download(FFMPEG_BASE + name, root / "downloads" / name, FFMPEG_SHA256[name], label=tool)
        d.mkdir(parents=True, exist_ok=True)
        tmp = exe.with_name(exe.name + ".part")
        with gzip.open(gz, "rb") as src, open(tmp, "wb") as out:
            shutil.copyfileobj(src, out)
        os.chmod(tmp, 0o755)
        os.replace(tmp, exe)
        gz.unlink(missing_ok=True)
    return d


# ---------------------------------------------------------------------------- shortcuts

def write_start_script(root: Path) -> Path:
    """The file shortcuts point at. Kept ASCII (cmd.exe code pages); Python prints the Chinese."""
    if WINDOWS:
        p = root / "LACUNA.cmd"
        p.write_text('@echo off\r\ntitle LACUNA\r\n"%~dp0venv\\Scripts\\python.exe" "%~dp0lacuna_launcher.py" run\r\n'
                     "if errorlevel 1 pause\r\n", encoding="ascii")
    else:
        p = root / "LACUNA.command"
        p.write_text('#!/bin/bash\nprintf "\\033]0;LACUNA\\007"\ncd "$(dirname "$0")"\n'
                     './venv/bin/python ./lacuna_launcher.py run || read -r -p "Press Enter to close" _\n',
                     encoding="ascii")
        os.chmod(p, 0o755)
    return p


ICONS = ("LACUNA.ico", "LACUNA.icns")


def install_icons(root: Path, app_dir: Path) -> bool:
    """Copy the app version's icons into the root. True when one changed (the shortcuts then need refreshing)."""
    changed = False
    for name in ICONS:
        src, dst = app_dir / "installer" / name, root / name
        if src.is_file() and (not dst.is_file() or dst.read_bytes() != src.read_bytes()):
            shutil.copyfile(src, dst)
            changed = True
    return changed


def ps_quote(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def make_shortcuts(root: Path, port: int, home: Path | None = None) -> list[Path]:
    """Windows: Desktop + Start menu shortcuts. macOS: ~/Applications/LACUNA.app. Linux: none."""
    start = write_start_script(root)
    made: list[Path] = []
    ico, icns = root / "LACUNA.ico", root / "LACUNA.icns"
    if WINDOWS:
        icon = f"$lnk.IconLocation = {ps_quote(str(ico) + ',0')}; " if ico.is_file() else ""
        script = (
            "$ws = New-Object -ComObject WScript.Shell; "
            "foreach ($dir in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) { "
            "  if (-not $dir) { continue }; $lnk = $ws.CreateShortcut((Join-Path $dir 'LACUNA.lnk')); "
            f"  $lnk.TargetPath = {ps_quote(start)}; $lnk.WorkingDirectory = {ps_quote(root)}; "
            f"  $lnk.Description = 'LACUNA Studio'; {icon}$lnk.Save(); Write-Output (Join-Path $dir 'LACUNA.lnk') }}")
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                             capture_output=True, text=True)
        made = [Path(x) for x in out.stdout.split("\n") if x.strip()]
    elif MACOS:
        app = (home or Path.home()) / "Applications" / "LACUNA.app"
        macos = app / "Contents" / "MacOS"
        macos.mkdir(parents=True, exist_ok=True)
        icon = ""
        if icns.is_file():
            (app / "Contents" / "Resources").mkdir(exist_ok=True)
            shutil.copyfile(icns, app / "Contents" / "Resources" / "LACUNA.icns")
            icon = "\n  <key>CFBundleIconFile</key><string>LACUNA</string>"
        (app / "Contents" / "Info.plist").write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>LACUNA</string>
  <key>CFBundleDisplayName</key><string>LACUNA</string>
  <key>CFBundleIdentifier</key><string>studio.lacuna.launcher</string>
  <key>CFBundleExecutable</key><string>LACUNA</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>LSUIElement</key><true/>{icon}
</dict></plist>
""", encoding="utf-8")
        exe = macos / "LACUNA"
        url = f"http://127.0.0.1:{port}/"
        # already running -> just show it; otherwise open the console window that runs it
        exe.write_text(f"""#!/bin/bash
if /usr/bin/curl -fsS -m 2 "{url}api/health" >/dev/null 2>&1; then
  open "{url}"
else
  open -a Terminal "{start}"
fi
""", encoding="utf-8")
        os.chmod(exe, 0o755)
        made = [app]
    return made


# ---------------------------------------------------------------------------- install

def install(root: Path, base: str, workspace: Path | None, port: int | None, zip_file: Path | None,
            start: bool = True, shortcuts: bool = True, runner=run_cmd) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    if not uv_path(root).is_file():
        raise LauncherError(f"{root} 里没有 uv，请用安装脚本（install.sh / install.ps1）安装。")
    old = read_json(root / "config.json") or {}
    ws = Path(workspace or old.get("workspace") or default_workspace()).expanduser()
    ws.mkdir(parents=True, exist_ok=True)
    port = int(port or old.get("port") or DEFAULT_PORT)

    if zip_file is None:
        feed = read_feed(base)
        say(f"下载 {APP} {feed['version']} …")
        zip_file = download(join_url(base, feed["zip"]), root / "downloads" / f"lacuna-{feed['version']}.zip",
                            feed["sha256"], label=APP)
    version, app_dir = extract_release(Path(zip_file), root / "versions")

    ensure_venv(root, runner)
    if not install_packages(root, app_dir, runner):
        raise LauncherError("安装组件失败（uv pip install），看上面的错误信息；检查网络后重新运行安装。")
    ensure_ffmpeg(root)

    me = Path(__file__).resolve()
    target = root / "lacuna_launcher.py"
    src = app_dir / "installer" / "lacuna_launcher.py"
    shutil.copyfile(src if src.is_file() else me, target)
    install_icons(root, app_dir)

    cfg = {"schema": CONFIG_SCHEMA, "workspace": str(ws), "port": port, "current": version,
           "previous": old.get("current") if old.get("current") != version else old.get("previous"),
           "feed": join_url(base, FEED_NAME), "installed": old.get("installed") or time.strftime("%Y-%m-%d %H:%M"),
           "shortcuts": shortcuts}
    write_json(root / "config.json", cfg)
    made = make_shortcuts(root, port) if shortcuts else [write_start_script(root)]
    prune_versions(root, cfg)
    say("")
    say(f"{APP} {version} 装好了。")
    say(f"  工作区：{ws}")
    for m in made:
        say(f"  启动：{m}")
    return cfg


def prune_versions(root: Path, cfg: dict) -> None:
    keep = {cfg.get("current"), cfg.get("previous")}
    vdir = root / "versions"
    if not vdir.is_dir():
        return
    for d in vdir.iterdir():
        if d.is_dir() and d.name not in keep:
            shutil.rmtree(d, ignore_errors=True)
    dl = root / "downloads"
    if dl.is_dir():
        for f in dl.glob("lacuna-*.zip"):
            f.unlink(missing_ok=True)


# ---------------------------------------------------------------------------- run

def health(port: int, timeout: float = 2.0) -> dict | None:
    """What /api/app says (version etc.), or None when nothing LACUNA-like answers."""
    try:
        d = json.loads(fetch_bytes(f"http://127.0.0.1:{port}/api/app", timeout=timeout))
        return d if isinstance(d, dict) and "version" in d else None
    except (OSError, ValueError):
        return None


def app_env(root: Path, cfg: dict) -> dict:
    env = dict(os.environ)
    env["PATH"] = str(ffmpeg_dir(root)) + os.pathsep + env.get("PATH", "")
    env.update(LACUNA_HOME=str(root), LACUNA_UPDATE_FEED=cfg.get("feed") or join_url(DEFAULT_BASE, FEED_NAME),
               PYTHONUTF8="1")
    env.pop("VIRTUAL_ENV", None)
    return env


def server_cmd(root: Path, cfg: dict, browser: bool) -> list:
    cmd = [venv_python(root), "-m", "lacuna_app", "--workspace", cfg["workspace"], "--port", str(cfg["port"])]
    return cmd + ([] if browser else ["--no-browser"])


def log_update(root: Path, entry: dict) -> None:
    entry = {"at": time.strftime("%Y-%m-%d %H:%M:%S")} | entry
    write_json(root / "update_log.json", {"last": entry})


def wait_healthy(proc: subprocess.Popen, port: int, version: str, timeout: float) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if proc.poll() is not None:
            return False
        h = health(port, timeout=2.0)
        if h and h.get("version") == version:
            return True
        time.sleep(0.5)
    return False


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def apply_pending(root: Path, cfg: dict, runner=run_cmd) -> tuple[dict, str | None]:
    """Switch config to the version the app prepared. Returns (config, version to verify or None)."""
    pend_file = root / "pending.json"
    pending = read_json(pend_file)
    pend_file.unlink(missing_ok=True)
    if not pending or not pending.get("version"):
        return cfg, None
    new = pending["version"]
    old = cfg.get("current")
    app_dir = root / "versions" / new
    if new == old or not (app_dir / "VERSION").is_file():
        log_update(root, {"ok": False, "from": old, "to": new, "message": "更新包不见了，没有更新。"})
        return cfg, None
    say(f"更新到 {new} …")
    if not install_packages(root, app_dir, runner):
        install_packages(root, root / "versions" / old, runner)
        log_update(root, {"ok": False, "from": old, "to": new, "message": "新版本的组件没装上，还在用原来的版本。"})
        return cfg, None
    cfg = cfg | {"current": new, "previous": old, "fallback": cfg.get("previous")}
    write_json(root / "config.json", cfg)
    return cfg, new


def rollback(root: Path, cfg: dict, runner=run_cmd) -> dict:
    bad, prev = cfg.get("current"), cfg.get("previous")
    if not prev or not (root / "versions" / prev / "VERSION").is_file():
        return cfg
    say(f"新版本 {bad} 没能正常启动，回到 {prev}。")
    install_packages(root, root / "versions" / prev, runner)
    # the failed version is dropped (a retry downloads it again); the fallback before it stays
    cfg = {k: v for k, v in cfg.items() if k != "fallback"} | {"current": prev, "previous": cfg.get("fallback"),
                                                              "failed": bad}
    write_json(root / "config.json", cfg)
    prune_versions(root, cfg)
    log_update(root, {"ok": False, "from": prev, "to": bad,
                      "message": f"新版本 {bad} 启动失败，已自动回到 {prev}。"})
    return cfg


def finish_update(root: Path, cfg: dict, version: str) -> None:
    log_update(root, {"ok": True, "from": cfg.get("previous"), "to": version, "message": f"已更新到 {version}。"})
    src = root / "versions" / version / "installer" / "lacuna_launcher.py"
    if src.is_file():                       # next start uses the new launcher
        shutil.copyfile(src, root / "lacuna_launcher.py")
    cfg.pop("failed", None)
    cfg.pop("fallback", None)
    write_json(root / "config.json", cfg)
    prune_versions(root, cfg)


def run(root: Path, browser: bool = True, runner=run_cmd, health_timeout: float = HEALTH_TIMEOUT) -> int:
    cfg = load_config(root)
    port = int(cfg["port"])
    url = f"http://127.0.0.1:{port}/"
    # a version with a new icon: refresh the shortcuts (installs from before the key had shortcuts)
    if install_icons(root, root / "versions" / cfg["current"]) and cfg.get("shortcuts", True):
        make_shortcuts(root, port)
    if health(port):
        say(f"{APP} 已经在运行，打开 {url}")
        if browser:
            webbrowser.open(url)
        return 0
    say(f"{APP} 正在运行（{url}）。关掉这个窗口就会退出 {APP}。")
    verify: str | None = None
    while True:
        app_dir = root / "versions" / cfg["current"]
        proc = subprocess.Popen([str(c) for c in server_cmd(root, cfg, browser)], cwd=app_dir, env=app_env(root, cfg))
        browser = False                     # the page is already open after the first start
        try:
            if verify:
                if wait_healthy(proc, port, verify, health_timeout):
                    finish_update(root, cfg, verify)
                    say(f"已更新到 {verify}。")
                else:
                    stop(proc)
                    cfg, verify = rollback(root, cfg, runner), None
                    continue
                verify = None
            code = proc.wait()
        except KeyboardInterrupt:
            stop(proc)
            return 0
        if code == UPDATE_EXIT:
            cfg, verify = apply_pending(root, cfg, runner)
            continue
        if code == RESTART_EXIT:
            continue
        return code


# ---------------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lacuna_launcher", description=f"{APP} launcher")
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("install")
    i.add_argument("--root", type=Path, default=Path(os.environ.get("LACUNA_ROOT") or default_root()))
    i.add_argument("--base", default=os.environ.get("LACUNA_RELEASE_BASE") or DEFAULT_BASE)
    i.add_argument("--workspace", type=Path, default=os.environ.get("LACUNA_WORKSPACE") or None)
    i.add_argument("--port", type=int, default=None)
    i.add_argument("--zip", type=Path, default=None, help="install this release zip instead of downloading")
    i.add_argument("--no-start", action="store_true", default=bool(os.environ.get("LACUNA_NO_START")))
    i.add_argument("--no-shortcuts", action="store_true", default=bool(os.environ.get("LACUNA_NO_SHORTCUTS")))
    r = sub.add_parser("run")
    r.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    r.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "install":
            install(args.root, args.base, args.workspace, args.port, args.zip, shortcuts=not args.no_shortcuts)
            if not args.no_start:
                return run(args.root)
            return 0
        return run(args.root, browser=not args.no_browser)
    except LauncherError as e:
        say(f"\n出错了：{e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
