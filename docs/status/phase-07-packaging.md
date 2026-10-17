# Phase 7 — 打包与更新

State: **built (D51)**; first Release + Leon's PC migration with the next batch update, then Pei installs on her Mac

What Leon gets: 双击更新（不再靠远程装机）、Mac 实机跑通（Pei）

Depends on: — (any time; best after 2) · Parallel with: any

## Progress
- **Phase 7 packaging + update built** (2026-10-17, D51): installer scripts (Mac one-line paste, Windows `LACUNA-Setup.cmd` / `install.ps1`), launcher with in-app update and automatic rollback, 「设置」page (version, update, API key incl. macOS Keychain, ffmpeg/model status), Release workflow. CI runs a real install → update → rollback on Win/Mac/Linux. Not yet: first Release, migrating Leon's PC (steps in `docs/INSTALL.md`), Pei's real Mac install. Desktop icon artwork is phase 8.

## How it is built (打包与更新 (2026-10-17, D51))
- Install: `installer/install.sh` (macOS/Linux, `curl … | bash`), `installer/install.ps1` + `LACUNA-Setup.cmd` (Windows) download uv → uv installs Python 3.12 → `installer/lacuna_launcher.py install`: release zip from `releases/latest/download/version.json` (sha256), venv + `.[claude,asr]`, ffmpeg/ffprobe 6.1.1 static (pinned sha256) in `<root>/ffmpeg`, config, shortcuts (Windows Desktop + Start menu → `LACUNA.cmd`; macOS `~/Applications/LACUNA.app` → Terminal running `LACUNA.command`). Roots: `%LOCALAPPDATA%\LACUNA`, `~/Library/Application Support/LACUNA`. Workspace default: `C:\Projects\LACUNA_Workspace` if present, else `~/LACUNA_Workspace`.
- Run: `lacuna_launcher.py run` starts `python -m lacuna_app` from `versions/<current>/` with `LACUNA_HOME`, `LACUNA_UPDATE_FEED` and the bundled ffmpeg first on PATH; already running → opens the browser only.
- Update: page 「设置」(`#/settings`, top-bar link shows 「有新版本」): 检查更新 / 下载新版本 (background, sha256, unpack to `versions/<v>/`) / 更新并重启 (refused while an import, export or publish pack runs) → server exits 75 → launcher installs the new version's packages, starts it, waits ≤ 180 s for `/api/app` to report the new version, else reinstalls and starts the previous one and logs it (`update_log.json`, shown on the page). Keeps current + previous. Exit 76 = plain restart.
- API key on 设置: Windows → `HKCU\Environment` (same as `setx`); macOS → login Keychain (service `LACUNA`); else a 0600 file in the install root. `find_api_key` reads env → registry → Keychain → file. Saving restarts the installed app so the AI clients pick it up.
- Release: Actions → **Release** (workflow_dispatch from main, Chinese notes) → tag `vYYYY.M.D.N`, assets `lacuna.zip`, `version.json`, installers, launcher (`installer/build_release.py`).
- API: `GET /api/app`, `POST /api/app/update/check|prepare|apply`, `POST /api/app/api-key`. Engine `lacuna_app/appinfo.py`.
- Tests: `tests/installer/test_launcher.py` (install, update, broken release rollback, failed package install, restart; fake uv + fake app), `tests/app/test_appinfo.py`, `web/e2e/settings.spec.ts`, CI job `install` = `tests/installer/smoke_install.py` on Windows / macOS / Linux (real installer, uv, Python, packages, ffmpeg download, in-app update, rollback).
- Steps for Leon / Pei: `docs/INSTALL.md`.

## Open issues
- Packaging (D51): a release that fails to start is rolled back but stays offered on 设置 until a newer one is released. Installs are per user and unsigned by design (no Apple developer account): Windows SmartScreen may warn on a downloaded `LACUNA-Setup.cmd` (the PowerShell one-liner avoids it).
- macOS: no real Mac run yet; the CI install job runs the real Mac installer + update + rollback. Pei's install steps: `docs/INSTALL.md`.
