# Desktop app retired: LACUNA is cloud-only

- Date: 2026-10-19
- Status: CONFIRMED (Leon, 2026-10-19: cloud-only from now on, no more desktop releases)
- Supersedes: D51 (installer + release zip + in-app update, phase 7) and the Release workflow; the
  "Releases are batched" convention in CLAUDE.md

## What
The installed desktop app is gone. Removed: `installer/` (launcher, `build_release.py`, `install.sh`,
`install.ps1`, `LACUNA-Setup.cmd`, desktop icons), `design/logo/` (it only generated those icons),
`.github/workflows/release.yml`, CI's `install` job and its path filters, `tests/installer/`, and the in-app
update: the `Updater` in `lacuna_app/appinfo.py`, `POST /api/app/update/{check,prepare,apply}`, exit codes
75/76 and the restart plumbing in `lacuna_app/__main__.py`, the update part of 设置 and the top bar's
「有新版本」, their tests, E2E fake and English strings. `docs/INSTALL.md` is now a short retired note.

## Why
Since 2026-10-19 LACUNA runs at https://lacunastudio.app (decision `cloud-deploy`) and Leon's workspace
has been moved there. Nobody installs the desktop app any more, and keeping the launcher, release
workflow and three-OS install smoke test alive costs CI time and review attention for nothing.

## What stays
- The cloud app and its deploy path: PR → staging (decision `staging-site`) → merge to main → Deploy.
- `/api/app` (version, `busy` list, key status) and `/api/health`: the host updater
  (`deploy/host/lacuna-update`) waits on `busy`, and the deploy health checks read the version.
- A development checkout: `python -m lacuna_app --workspace …` on localhost (opens the browser, saves an API
  key from 设置, `LACUNA_HOME` / `~/.config/lacuna` for key files), and CI's Windows / macOS / Linux matrix
  so it keeps working on Leon's and Pei's machines.
- The logo (`web/src/features/brand/logo.svg`) for the favicon and the interface.
