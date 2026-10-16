# Roadmap — ordered, gated and testable

## Phase 0 — Seamless handoff and context persistence

- Read entire package; create `CLAUDE.md`, decision registry, risks, project state, task tracker.
- Produce brief context audit, confirm no contradictions, mark confirmed/assumed/unverified.
- Set up repo and local workspace conventions without prematurely committing to a heavyweight stack.
- Deliverable: durable project context, prioritized backlog and first spike plan.

## Phase 1 — Technical feasibility (must pass before major build)

**1A. Claude Code Bridge:** official support/plan/CLI/auth/session/cost/structured response test. **STOP and consult user if personal-plan/no-extra-API-cost requirement cannot be met.**

**1B. Audio proof:** small real dual-track sample; ASR/alignment, overlap editing, non-destructive EDL, localized render/undo; benchmark both OSes when accessible.

**1C. Historical raw/final:** 1–2 raw/final pairs; identify observable cuts/moves with confidence, document failure cases and holdout strategy.

Gate: publish evidence-based feasibility report and minimal architecture recommendation.

## Phase 2 — UX discovery and prototype

- User journey map, screen architecture, low-fidelity then clickable prototype.
- Demonstrate local import, AI producer chat, status/dependency board, asset request, Full Listen / Edit Review, contextual local preview, rule suggestion.
- Review with user on **creative interaction** only; routine controls are designer's job.

Gate: user approves primary journey, not every visual detail.

## Phase 3 — Core vertical slice

- Local episode/project persistence, dual-track import and diagnostics.
- Whole-episode analysis, source-faithful first-cut proposal, versioned EDL and renderer.
- Full Listen + Edit Review player, time-anchored feedback, local preview -> approve -> commit, undo/export.
- Test and demo on real short episode excerpt.

Gate: user can complete meaningful review without manual Audacity micro-edits.

## Phase 4 — Production orchestration and sound design

- Task DAG, persistence, resume, missing asset inbox/watch, file indexing/metadata.
- Series jingle defaults, music suggestions, source ranges from actual assets, background mixing/ducking, film clip insertion.
- Clear status, exception-based review and crash recovery.

## Phase 5 — Personalization and history

- Batch raw/final import, robust alignment, inferred candidate rules, approval/versioning.
- Holdout evaluation, preference calibration and false-deletion regression.

## Phase 6 — Publishing and packaging

- Mastering/export, chapters, show notes, artwork workflow.
- Assisted 喜马拉雅 publication; optionally investigate official API/Playwright separately.
- Windows/macOS install/update experience, readiness checks, portability tests, partner handoff.

## Phase 7 — Real-episode acceptance and iteration

- Run full realistic ~2h episode, collect active human time, AI elapsed time, approval burden, audio issues and actual editorial acceptance.
- Target 1–2h human involvement, 3h ceiling. Optimize based on observed bottlenecks, not vanity edit counts.

## Anti-patterns

- Building all screens before validating the Claude integration gate.
- Running expensive whole-episode processing before proving 5–15 minute pipeline.
- Relying on the user to manually test core audio processing.
- Treating mock UX as production proof.
- Shipping destructive edits or silent changes to spoken words.
- Reopening settled scope or proposing cloud hosting for V1.
