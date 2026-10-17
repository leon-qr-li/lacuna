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
- UX wireframes: https://claude.ai/artifact/1BvHmxW54dWCS9kFPyumqV (`design/wireframes/`).
- **AI first cut in the app** (2026-10-17): `lacuna_app/ai_cut.py` + `scripts/make_ai_episode.py` turn S5 edit ops into reviewable edits (title "EP001 · AI 第一刀", no demo marks). Review = content / conf < 0.6 / > 1.5 s speech, content first then by duration (`lacuna_app/review.py`, D33). v2 held-out ops on full EP001: 384 ops → 367 edits (163 to review), 17 skipped (same pause positions the S5 scorer rejects), 73:32 → 67:08. Episode timeline now derived in one batch sweep (`lacuna_core.apply_batch`): ~570-edit episode opens in ~150 ms, restore/undo ~90 ms, A/B ≤ 0.4 s, server RSS < 0.5 GB. Screenshot `screenshots/04_ai_cut_review.png`.

## Open issues
- Content-trim selection is taste: needs ranked review + learning from Leon's restores (D27), not more rules.
- Pause shaping too uniform (keeps 2 vs Leon's 41 pauses >1 s); interjection moves should come from asymmetric per-track pause cuts.
- Chat is mock only until ClaudeEditorAdapter is wired with Leon's API key (key stays on his PC).
- One-track `tighten_pause` while the other host talks is skipped (needs per-track re-timing in the episode model); counted in `ai_report`. No per-track loudness edit in the AI path yet (D31).
- Review list is long with the v2 confidences (~45 % of edits under 0.6, incl. 41 pauses): tune the threshold or the AI's calibration once Leon has reviewed one episode.
- Missing: export + mastering/LUFS, task panel, asset inbox, topic labels, stereo music bus, CI matrix, macOS test.

## Next action
1. When `ai_v3_full_ops.json` lands: `python scripts/make_ai_episode.py --workspace <ws> --ops spikes/s5_first_cut/out/ai_v3_full_ops.json` on Leon's PC; Leon reviews it.
2. Wire real ClaudeEditorAdapter (API key via local env/config on Leon's PC).
3. Export with mastering (leveller + LUFS/true-peak).
