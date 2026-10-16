# AI-Native Podcast Studio — Claude Code Handoff

**Status:** Product discovery completed; technical feasibility and UX design are NEXT.  
**Date:** 2026-10-16  
**Owner:** Podcast creator / product owner  
**Implementation agent:** Claude Code with Opus 5.5 (preferred; verify actual availability)  
**Language:** Discuss with product owner in natural Chinese; technical artifacts may be English.

## Start here

1. Read `01_MASTER_HANDOFF_PROMPT.md` and **all** linked documents before proposing code.
2. Treat `02_PRODUCT_REQUIREMENTS.md` and `03_EDITORIAL_PLAYBOOK.md` as authoritative product intent; `07_DECISION_LOG.md` records the precise decision history and superseded assumptions.
3. Do not ask the user to repeat decisions recorded in this package. Raise only genuine blockers, new tradeoffs, or creative decisions.
4. First deliver an understanding/assumptions audit, feasibility plan, and UX journey/wireframe plan. Run small proofs of concept before committing to architecture or full implementation.
5. Preserve context across Claude sessions in repository documentation (`CLAUDE.md`, decision log, task status, and tests); never rely on chat context alone.

## File map

- `01_MASTER_HANDOFF_PROMPT.md` — Paste into Claude Code / Claude Project as kickoff.
- `02_PRODUCT_REQUIREMENTS.md` — PRD, scope, outcomes, functional requirements.
- `03_EDITORIAL_PLAYBOOK.md` — Style, sound design, two-track editing, memory.
- `04_USER_JOURNEYS_AND_UX.md` — Primary flows, screens, interactions, states.
- `05_TECHNICAL_FEASIBILITY.md` — Hard constraints, risks, PoCs, architecture hypotheses.
- `06_QUALITY_AND_ACCEPTANCE.md` — Testing ownership, evaluation, success criteria.
- `07_DECISION_LOG.md` — Confirmed decisions, corrections, open questions.
- `08_IMPLEMENTATION_ROADMAP.md` — Execution order, gates, deliverables.
- `09_SESSION_CONTINUITY.md` — How to maintain context and hand off between sessions.

## Golden rule

> **Preserve the conversation. Polish the delivery.**

The app is an **interactive AI producer**, not a DAW clone, not a text-summarization machine, and not an unattended auto-publisher.
