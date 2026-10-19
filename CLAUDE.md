# LACUNA Studio

Local-first AI podcast producer for the two-host Chinese film podcast 《洛城二三事》. Runs in the cloud at https://lacunastudio.app (Docker image); a development checkout runs on localhost.

**Golden rule: Preserve the conversation. Polish the delivery. Remove awkwardness, not personality.**

## Read first (every session)
1. `docs/PROJECT_STATUS.md` — index of the status files; then your phase's or area's `docs/status/…md` (state, blockers, next action).
2. Decisions: `docs/decisions/` (one file each, newest) and `docs/DECISIONS.md` (D23–D51, frozen; D01–D22 in `docs/handoff/07_DECISION_LOG.md`).
3. `docs/00_TECH_LEAD_ASSESSMENT.md` — risks, architecture hypothesis, roadmap.
4. `docs/HARDWARE_PROFILE.md` — hard resource constraints (GTX 1660S 6GB, 16GB RAM).
5. `docs/PARALLEL_WORK.md` — where a feature puts its code and docs so parallel threads don't conflict; git routine.
6. `docs/handoff/` — immutable product-discovery baseline. PRD (02) and Editorial Playbook (03) are authoritative product intent.

## Non-negotiables
- Never add words / synthetic speech; edits reference source audio ranges only.
- Original audio is read-only; all edits non-destructive (EDL).
- Runtime AI = Claude API via Max-included API credits (D23). Never use subscription OAuth in product code.
- Audio and user media never go to the AI; only text + numeric features go to the API. In the cloud they stay on our own server (encrypted volume + encrypted off-site backup; decision `cloud-deploy`).
- Claude owns QA: every change ships with automated tests.
- Users never see the AI vendor: interface text (zh + en), AI replies and errors call the AI "LACUNA", never Claude / Anthropic (decision `ai-called-lacuna`; checked by `npm run build`, `tests/test_brand_text.py`, `web/e2e/brand_text.spec.ts`). Code, identifiers, env vars and engineering docs are unaffected.

## Conventions
- Talk to Leon in Chinese (简体中文); code, identifiers and engineering docs may be English.
- End every session by updating your phase's file in `docs/status/`; write each new decision as its own file in `docs/decisions/` (no D-number). Don't append to `PROJECT_STATUS.md`, `ROADMAP.md` or `DECISIONS.md`.
- Interface text: Chinese in `t()` (web) / `tr()` (server) with English in the feature's `en.ts` (server: `lacuna_app/i18n_en.py`); `npm run build` and `tests/test_i18n.py` fail on bare Chinese. Episode content (transcripts, show notes) stays Chinese.
- Confirmations and notices use the in-app dialog (`confirmDialog` / `noticeDialog` in `web/src/features/dialog/Dialog.tsx`), never the browser's `confirm` / `alert` / `prompt` (`npm run build` checks).
- Deploys go PR → staging → production: a change Leon will see gets the `staging` label, Leon checks it on preview.lacunastudio.app, and merging to main ships it (`docs/PARALLEL_WORK.md`, decision `staging-site`). No desktop releases (decision `desktop-retired`).
- A new feature adds its own files (route module, web feature folder, E2E fake module, CSS) instead of editing shared ones; see `docs/PARALLEL_WORK.md`.
