# LACUNA Studio — Project Status

_Last updated: 2026-10-17 02:20Z_

## Current phase
POC passed (Leon, 2026-10-17). Building the app in small phases per `docs/ROADMAP.md` (D34). App phase 1 (审阅提速) done and validated by Leon on his PC (main a719a8a). Mastering + export merged (#4). Phase 3 (real AI chat) merged (#8); to be installed on Leon's PC together with the phase 1 playhead fix (#7).

## Done
- Assessment `docs/00_TECH_LEAD_ASSESSMENT.md`; decisions `docs/DECISIONS.md` (D23–D32); hardware `docs/HARDWARE_PROFILE.md`; editorial rules `docs/EDITORIAL_RULES.md` (R001–R003).
- Workspace on Leon's PC: `C:\Projects\LACUNA_Workspace\` (EP001 raw + reference). EP001 is a full raw/final pair (D29).
- Spikes: S2 ASR → Paraformer (D30); S4 alignment → 470 cuts, per-track editing (D31); S3 engine `lacuna_core/` (0 clicks, 204× RT).
- S5 AI first cut: v1 blind (too conservative) → v2 with rules learned from first half, scored on held-out half: length 1830 s vs Leon 1806 s, event recall L/P 0.71/0.79, but content-trim precision 0.44. See `spikes/s5_first_cut/REPORT.md`.
- App vertical slice (`lacuna_app/` + `web/`): full listen, voice/chat change → A/B preview → approve, edit review, restore/undo. Demo episode = EP001 10:00–20:00 with Leon's real cut positions.
- **Installed and running on Leon's Windows PC** (2026-10-17): `C:\Projects\lacuna`, start with `C:\Projects\LACUNA_Start.bat` → http://127.0.0.1:8765/. 57/57 tests pass there incl. EP001 integration. Windows fixes in PR #1 (awaiting Leon's merge).
- CI (`.github/workflows/ci.yml`): every PR/push to main runs pytest, UI build and Playwright E2E on windows-latest, macos-latest (Apple Silicon) and ubuntu-latest. First Mac run caught ffmpeg builds without libsoxr; `conform()` now falls back to high-quality swr.
- UX wireframes: https://claude.ai/artifact/1BvHmxW54dWCS9kFPyumqV (`design/wireframes/`).
- **AI first cut in the app** (2026-10-17): `lacuna_app/ai_cut.py` + `scripts/make_ai_episode.py` turn S5 edit ops into reviewable edits (title "EP001 · AI 第一刀", no demo marks). Review = content / interjection / > 1.5 s speech / non-pause conf < 0.4, content first then by duration (`lacuna_app/review.py`, D33). v2 held-out ops on full EP001: 384 ops → 367 edits (163 to review), 17 skipped (same pause positions the S5 scorer rejects), 73:32 → 67:08. Episode timeline now derived in one batch sweep (`lacuna_core.apply_batch`): ~570-edit episode opens in ~150 ms, restore/undo ~90 ms, A/B ≤ 0.4 s, server RSS < 0.5 GB. Screenshot `screenshots/04_ai_cut_review.png`.

- **On Leon's PC** (2026-10-17, main 7bc041e): episode `EP001_AI` ("EP001 · AI 第一刀", v3 ops) built in `C:\Projects\LACUNA_Workspace`: 646 edits, 114 to review, 73:32 → 59:43; 107/107 pytest there. Start with `C:\Projects\LACUNA_Start.bat`.
- **Mastering + export** (2026-10-17, D36): top-bar 导出 → stereo 24-bit WAV + 128 kbps MP3 in `<workspace>/exports/<episode>/` (+ JSON record), -16 LUFS / ≤ -1 dBTP, gentle chain (`lacuna_core/master.py`, `export.py`, `lacuna_app/exporter.py`). Validated on Leon's PC with full raw EP001 (Leon +7 dB): in -17.4 LUFS / +5.5 dBTP → out -16.14 LUFS / -1.30 dBTP; compressor mean 0.95 dB; limiter active 0.5 %; MP3 -16.6 LUFS / -1.46 dBTP; 73.5 min in ~5 min, ~145 MB RAM. Leon's own 最终成品.mp3 measures -17.9 LUFS / +4.4 dBTP (clipping). Listening pair in `exports\EP001_mastering_test\` (A_before_preview / B_after_master, from 60:22).

## Open issues
- `EP001_demo` now shows 0 to review under the D33 rule (its fake confidences are ≥ 0.45, no content category). Demo is superseded by EP001_AI; delete or regenerate it.
- Content-trim selection is taste: needs ranked review + learning from Leon's restores (D27), not more rules.
- Pause shaping too uniform (keeps 2 vs Leon's 41 pauses >1 s); interjection moves should come from asymmetric per-track pause cuts.
- Phase 3 (real Claude chat, D37) merged; real-key check on Leon's PC via `scripts/ai_chat_smoke.py`. Cost per chat turn is logged to `<workspace>/ai_usage.jsonl`.
- One-track `tighten_pause` while the other host talks is skipped (needs per-track re-timing in the episode model); counted in `ai_report`. No per-track loudness edit in the AI path yet (D31).
- Review threshold (D33) tuned to v3: 114 of 646 edits to review. AI confidences are poorly calibrated (almost all 0.5–0.6); recalibrate from Leon's first full review.
- Mastering: MP3 comes out ~0.4 LU quieter than the WAV (LAME low-pass); app preview still soft-clips (preview is not mastered). Tuning of compressor/limiter awaits Leon's listening verdict.
- Missing: task panel, asset inbox, topic labels, stereo music bus. macOS is verified only by CI (no real Mac run yet).

## Next action
0. Phase 3 (real chat) per ROADMAP; then phase 4 (new-episode import). Phase 2 (export) shipped with #4.
1. Leon reviews "EP001 · AI 第一刀" (v3, full episode) on his PC; learn from his restores/approvals (D27) and recalibrate review threshold + content-trim taste.
2. Leon sets ANTHROPIC_API_KEY (steps given 2026-10-17; anthropic SDK installed on his PC) → verify real chat end to end.
3. Leon listens to the mastering A/B and an exported EP001_AI; tune chain if needed.
