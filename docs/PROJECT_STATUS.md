# LACUNA Studio — Project Status

_Last updated: 2026-10-17 01:00Z_

## Current phase
P1: runnable vertical slice exists, AI first cut calibrated on EP001. Direction confirmed (D23 API credits path, D24 narrowed MVP).

## Done
- Assessment `docs/00_TECH_LEAD_ASSESSMENT.md`; decisions `docs/DECISIONS.md` (D23–D32); hardware `docs/HARDWARE_PROFILE.md`; editorial rules `docs/EDITORIAL_RULES.md` (R001–R003).
- Workspace on Leon's PC: `C:\Projects\LACUNA_Workspace\` (EP001 raw + reference). EP001 is a full raw/final pair (D29).
- Spikes: S2 ASR → Paraformer (D30); S4 alignment → 470 cuts, per-track editing (D31); S3 engine `lacuna_core/` (0 clicks, 204× RT).
- S5 AI first cut: v1 blind (too conservative) → v2 with rules learned from first half, scored on held-out half: length 1830 s vs Leon 1806 s, event recall L/P 0.71/0.79, but content-trim precision 0.44. See `spikes/s5_first_cut/REPORT.md`.
- App vertical slice (`lacuna_app/` + `web/`): full listen, voice/chat change → A/B preview → approve, edit review, restore/undo. Demo episode = EP001 10:00–20:00 with Leon's real cut positions.
- **Installed and running on Leon's Windows PC** (2026-10-17): `C:\Projects\lacuna`, start with `C:\Projects\LACUNA_Start.bat` → http://127.0.0.1:8765/. 57/57 tests pass there incl. EP001 integration. Windows fixes in PR #1 (awaiting Leon's merge).
- CI (`.github/workflows/ci.yml`): every PR/push to main runs pytest, UI build and Playwright E2E on windows-latest, macos-latest (Apple Silicon) and ubuntu-latest. First Mac run caught ffmpeg builds without libsoxr; `conform()` now falls back to high-quality swr.
- UX wireframes: https://claude.ai/artifact/1BvHmxW54dWCS9kFPyumqV (`design/wireframes/`).

## Open issues
- Content-trim selection is taste: needs ranked review + learning from Leon's restores (D27), not more rules.
- Pause shaping too uniform (keeps 2 vs Leon's 41 pauses >1 s); interjection moves should come from asymmetric per-track pause cuts.
- Chat is mock only until ClaudeEditorAdapter is wired with Leon's API key (key stays on his PC).
- Missing: export + mastering/LUFS, task panel, asset inbox, topic labels, SlipRegion moves, stereo music bus. macOS is verified only by CI (no real Mac run yet).

## Next action
1. Feed v2 AI cut (full episode) into the app instead of the demo cut; content trims ranked for review.
2. Wire real ClaudeEditorAdapter (API key via local env/config on Leon's PC).
3. Export with mastering (leveller + LUFS/true-peak).
