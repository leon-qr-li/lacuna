# Foundation: POC, AI first cut, Leon's PC, CI

Cross-cutting state that belongs to no single phase.

## Done
- Assessment `docs/00_TECH_LEAD_ASSESSMENT.md`; decisions `docs/DECISIONS.md` (D23–D51, frozen; newer ones one file each in `docs/decisions/`); hardware `docs/HARDWARE_PROFILE.md`; editorial rules `docs/EDITORIAL_RULES.md` (R001–R003).
- Workspace on Leon's PC: `C:\Projects\LACUNA_Workspace\` (EP001 raw + reference). EP001 is a full raw/final pair (D29).
- Spikes: S2 ASR → Paraformer (D30); S4 alignment → 470 cuts, per-track editing (D31); S3 engine `lacuna_core/` (0 clicks, 204× RT).
- S5 AI first cut: v1 blind (too conservative) → v2 with rules learned from first half, scored on held-out half: length 1830 s vs Leon 1806 s, event recall L/P 0.71/0.79, but content-trim precision 0.44. See `spikes/s5_first_cut/REPORT.md`.
- App vertical slice (`lacuna_app/` + `web/`): full listen, voice/chat change → A/B preview → approve, edit review, restore/undo. Demo episode = EP001 10:00–20:00 with Leon's real cut positions.
- **Installed and running on Leon's Windows PC** (2026-10-17): `C:\Projects\lacuna`, start with `C:\Projects\LACUNA_Start.bat` → http://127.0.0.1:8765/. 57/57 tests pass there incl. EP001 integration. (Superseded: Leon's PC now runs the installed release and updates in-app, see phase 7; `C:\Projects\lacuna` is a dev copy.) Windows fixes in PR #1 (merged 2026-10-17).
- CI (`.github/workflows/ci.yml`): runs only what a change can affect: docs-only → nothing; `web/` only → UI build + E2E; Python → pytest + build + E2E; installer / pyproject → also a real install + update + rollback; CI config/unknown → all. Whatever runs, runs on windows/macos (Apple Silicon)/ubuntu. Merge gate = the single **CI ok** check (green also when nothing needed to run). Since #102 pytest (`-n auto`) and two E2E shards run as parallel jobs per OS and runs on main are never cancelled; timings in `docs/status/ci.md`. Claude merges its own PRs when CI ok is green (Leon, 2026-10-17).
- UX wireframes: https://claude.ai/artifact/1BvHmxW54dWCS9kFPyumqV (`design/wireframes/`).
- **AI first cut in the app** (2026-10-17): `lacuna_app/ai_cut.py` + `scripts/make_ai_episode.py` turn S5 edit ops into reviewable edits (title "EP001 · AI 第一刀", no demo marks). Review = content / interjection / > 1.5 s speech / non-pause conf < 0.4, listed in timeline order (`lacuna_app/review.py`, D33; order changed by D47). v2 held-out ops on full EP001: 384 ops → 367 edits (163 to review), 17 skipped (same pause positions the S5 scorer rejects), 73:32 → 67:08. Episode timeline now derived in one batch sweep (`lacuna_core.apply_batch`): ~570-edit episode opens in ~150 ms, restore/undo ~90 ms, A/B ≤ 0.4 s, server RSS < 0.5 GB. Screenshot `screenshots/04_ai_cut_review.png`.
- **On Leon's PC** (2026-10-17, main 7bc041e): episode `EP001_AI` ("EP001 · AI 第一刀", v3 ops) built in `C:\Projects\LACUNA_Workspace`: 646 edits, 114 to review, 73:32 → 59:43; 107/107 pytest there. Start with `C:\Projects\LACUNA_Start.bat`.
- Console noise (`lacuna_app/quiet.py`, PR #46 + 2026-10-17 follow-up): browser hang-ups (WinError 10054/10053, broken pipe, asyncio "socket.send() raised exception.", uvicorn "Exception in ASGI application" for a pure disconnect) are filtered from the `asyncio` and `uvicorn.error` loggers. Never hidden: failed `accept()` (asyncio closes the listening socket) and any non-disconnect error. `tests/app/test_quiet.py` includes a real uvicorn server aborted with TCP RST, so Windows CI exercises the Proactor path.

## Open issues
- `EP001_demo` now shows 0 to review under the D33 rule (its fake confidences are ≥ 0.45, no content category). Demo is superseded by EP001_AI; delete or regenerate it.
- Pause shaping too uniform (keeps 2 vs Leon's 41 pauses >1 s); interjection moves should come from asymmetric per-track pause cuts.
- One-track `tighten_pause` while the other host talks is skipped (needs per-track re-timing in the episode model); counted in `ai_report`. The AI first cut makes no loudness edits (D31); host levels are evened out separately at import with one `track_gain` per track (`levels.md`).
- Review threshold (D33) tuned to v3: 114 of 646 edits to review. AI confidences are poorly calibrated (almost all 0.5–0.6); recalibrate from Leon's first full review.
- Missing: asset inbox, topic labels (the task panel exists: import jobs, phase 4). macOS is verified only by CI (no real Mac run yet; see phase 7).
