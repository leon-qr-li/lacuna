# Brand / logo

**State (2026-10-17):** done: PR #70, shipped in 2026.10.17.7, **validated by Leon 20:24Z**. Logo V3「光晕」chosen by Leon (decision `docs/decisions/2026-10-17-logo.md`).
In the app: favicon, top-bar mark, sign-in brand panel, Windows shortcut icon, macOS LACUNA.app icon.

- Files: `web/src/features/brand/logo.svg` (+ README), `installer/LACUNA.ico|icns`, generator `design/logo/`.
- Tests: `web/e2e/brand.spec.ts` (favicon + top bar served from the bundled svg),
  `tests/installer/test_launcher.py` (icons copied on install, shortcut icon on Windows / .app icon on
  macOS, shortcuts refreshed once after an icon change).
- Validation on Leon's PC (passed): the browser tab shows the new icon; the top bar shows
  the logo left of LACUNA; after closing the LACUNA window and starting it again from the desktop, the
  desktop shortcut shows the new icon (Windows may need a moment to refresh its icon cache).
- Open: none.
