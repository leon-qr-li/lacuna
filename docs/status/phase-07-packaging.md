# Phase 7 — 打包与更新

State: **RETIRED 2026-10-19** (decision `docs/decisions/2026-10-19-desktop-retired.md`): LACUNA is cloud-only; installer, launcher, Release workflow and in-app update were removed. The notes below are history.

Earlier state: DONE, validated by Leon 2026-10-17 (Windows); Pei's Mac install waits for Leon's onboarding package

What Leon gets: 双击更新（不再靠远程装机）、Mac 实机跑通（Pei）

Depends on: — (any time; best after 2) · Parallel with: any

## Progress
- **Phase 7 packaging + update built** (2026-10-17, D51): installer scripts (Mac one-line paste, Windows `LACUNA-Setup.cmd` / `install.ps1`), launcher with in-app update and automatic rollback, 「设置」page (version, update, API key incl. macOS Keychain, ffmpeg/model status), Release workflow. CI runs a real install → update → rollback on Win/Mac/Linux. Desktop icon artwork: done with the logo (`brand.md`).
- **Released + validated** (2026-10-17): v2026.10.17.1 (first Release) installed on Leon's PC (`C:\Users\liqin\AppData\Local\LACUNA`, workspace `C:\Projects\LACUNA_Workspace`, port 8765; `C:\Projects\LACUNA_Start.bat` now calls `%LOCALAPPDATA%\LACUNA\LACUNA.cmd`, old one kept as `LACUNA_Start.old.bat`). v2026.10.17.2 (phase 11 upload page + #44) reached his PC through the in-app one-click update; Leon: "Verify it works". From now on Leon's PC updates only via Release + 设置 → 更新 (no git pull / RC installs). `C:\Projects\lacuna` is only a dev copy.
- #44 (2026-10-17): fixed a race in the install smoke test (the new version answers before the launcher logs the update) that turned main red on macOS/Windows; the 设置 page now waits for the launcher's log entry for the target version, so it also refreshes after a rollback instead of waiting 10 min.
- 2026-10-18 fix: updating 2026.10.17.10 → 2026.10.18.1 on Leon's PC hung at 「正在更新并重启」 and the page could not be reached: the old server stopped listening but never exited, because uvicorn's graceful shutdown waited forever for an open WAV stream (a paused `<audio>` in another tab). Now open connections get 3 s (`timeout_graceful_shutdown`), and the process force-exits 20 s after a restart request (`lacuna_app/__main__.py` `GRACEFUL_SHUTDOWN` / `FORCE_EXIT`, PR #84, test `tests/app/test_main_shutdown.py`). Shipped in 2026.10.18.2; updating *to* it still needed the workaround (close the other LACUNA tabs before 「更新并重启」), later updates do not.

## How it is built (打包与更新 (2026-10-17, D51))
- Install: `installer/install.sh` (macOS/Linux, `curl … | bash`), `installer/install.ps1` + `LACUNA-Setup.cmd` (Windows) download uv → uv installs Python 3.12 → `installer/lacuna_launcher.py install`: release zip from `releases/latest/download/version.json` (sha256), venv + `.[claude,asr]`, ffmpeg/ffprobe 6.1.1 static (pinned sha256) in `<root>/ffmpeg`, config, shortcuts (Windows Desktop + Start menu → `LACUNA.cmd`; macOS `~/Applications/LACUNA.app` → Terminal running `LACUNA.command`). Roots: `%LOCALAPPDATA%\LACUNA`, `~/Library/Application Support/LACUNA`. Workspace default: `C:\Projects\LACUNA_Workspace` if present, else `~/LACUNA_Workspace`.
- Run: `lacuna_launcher.py run` starts `python -m lacuna_app` from `versions/<current>/` with `LACUNA_HOME`, `LACUNA_UPDATE_FEED` and the bundled ffmpeg first on PATH; already running → opens the browser only.
- Update: page 「设置」(`#/settings`, top-bar link shows 「有新版本」): 检查更新 / 下载新版本 (background, sha256, unpack to `versions/<v>/`) / 更新并重启 (refused while an import, export or publish-pack generation runs) → server exits 75 → launcher installs the new version's packages, starts it, waits ≤ 180 s for `/api/app` to report the new version, else reinstalls and starts the previous one and logs it (`update_log.json`, shown on the page). Keeps current + previous. Exit 76 = plain restart.
- API key on 设置 (section 「AI 密钥」): Windows → `HKCU\Environment` (same as `setx`); macOS → login Keychain (service `LACUNA`); else a 0600 file in the install root. `find_api_key` reads env → registry → Keychain → file. Saving restarts the installed app so the AI clients pick it up.
- Release: Actions → **Release** (workflow_dispatch from main, Chinese notes) → tag `vYYYY.M.D.N`, assets `lacuna.zip`, `version.json`, installers, launcher (`installer/build_release.py`).
- API: `GET /api/app`, `POST /api/app/update/check|prepare|apply`, `POST /api/app/api-key`. Engine `lacuna_app/appinfo.py`.
- Tests: `tests/installer/test_launcher.py` (install, update, broken release rollback, failed package install, restart; fake uv + fake app), `tests/app/test_appinfo.py`, `web/e2e/settings.spec.ts`, CI job `install` = `tests/installer/smoke_install.py` on Windows / macOS / Linux (real installer, uv, Python, packages, ffmpeg download, in-app update, rollback).
- Steps for Leon / Pei: `docs/INSTALL.md`.

## Open issues
- Packaging (D51): a release that fails to start is rolled back but stays offered on 设置 until a newer one is released. Installs are per user and unsigned by design (no Apple developer account): Windows SmartScreen may warn on a downloaded `LACUNA-Setup.cmd` (the PowerShell one-liner avoids it).
- macOS: no real Mac run yet; the CI install job runs the real Mac installer + update + rollback. Pei's install steps: `docs/INSTALL.md`; Leon will send them to Pei himself as part of an onboarding package when the app is further along.
- On Leon's PC the key is reported as source `env` (the user env var is inherited by the window), not `registry-user`; both work.
