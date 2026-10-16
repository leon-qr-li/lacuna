# LACUNA Studio

Local-first AI podcast producer for the two-host Chinese film podcast 《洛城二三事》. Runs on Windows + macOS, browser UI on localhost.

**Golden rule: Preserve the conversation. Polish the delivery. Remove awkwardness, not personality.**

## Read first (every session)
1. `docs/PROJECT_STATUS.md` — current phase, blockers, exact next action.
2. `docs/DECISIONS.md` — D23+ (D01–D22 in `docs/handoff/07_DECISION_LOG.md`).
3. `docs/00_TECH_LEAD_ASSESSMENT.md` — risks, architecture hypothesis, roadmap.
4. `docs/HARDWARE_PROFILE.md` — hard resource constraints (GTX 1660S 6GB, 16GB RAM).
5. `docs/handoff/` — immutable product-discovery baseline. PRD (02) and Editorial Playbook (03) are authoritative product intent.

## Non-negotiables
- Never add words / synthetic speech; edits reference source audio ranges only.
- Original audio is read-only; all edits non-destructive (EDL).
- Runtime AI = Claude API via Max-included API credits (D23). Never use subscription OAuth in product code.
- Audio and user media never leave the machine; only text + numeric features go to the API.
- Claude owns QA: every change ships with automated tests.

## Conventions
- Talk to Leon in Chinese (简体中文); code, identifiers and engineering docs may be English.
- End every session by updating `docs/PROJECT_STATUS.md`; append new decisions to `docs/DECISIONS.md`.
