# Session Continuity Protocol — do not lose context

The user explicitly requests a **seamless handoff**. Context must survive compaction, new Claude sessions, computer restarts, and implementation-agent changes.

## On first import

1. Copy/retain this handoff folder in repository `docs/handoff/` unchanged as an immutable baseline (version it).
2. Create root `CLAUDE.md` with a short authoritative summary and links to the detailed documents; avoid copying contradictory partial summaries.
3. Create living documents:
   - `docs/DECISIONS.md`: append-only ADR/decision log, with status and supersession.
   - `docs/PROJECT_STATUS.md`: completed work, tests/evidence, current blockers, exact next action.
   - `docs/OPEN_QUESTIONS.md`: only unresolved issues, ranked by urgency, with owners.
   - `docs/EDITORIAL_RULES.md`: approved global/series rules, examples and version history.
   - `docs/ARCHITECTURE.md`: evidence-backed choices and changes.
   - `docs/TEST_PLAN.md`: automation strategy and acceptance evidence.
4. Maintain a traceability map from product requirements to code, tests and UX screens.

## At start of every Claude Code session

- Read `CLAUDE.md`, `docs/PROJECT_STATUS.md`, recent `docs/DECISIONS.md` and relevant requirements.
- Identify the exact next incomplete milestone and blockers.
- Do not ask already-answered questions; do not assume old proposed designs are confirmed.
- Verify actual repo state/tests rather than relying on narrative summaries.

## At end of every session

Update `docs/PROJECT_STATUS.md` with:

- What changed (file paths, decisions, UX artifacts).
- Commands/tests run and results; what was NOT tested.
- Open issues, risks, user decisions needed.
- The **next concrete action** and exact prerequisites.
- If there is a significant new user instruction, add to decision log with scope and whether it supersedes older assumptions.

## When new ChatGPT-generated UX or user-journey prompts arrive

Treat them as proposed amendments, compare against current confirmed requirements, note conflicts, and update decision log and acceptance criteria after user confirmation. Preserve existing intent; do not blindly overwrite rules or erase provenance.

## First-turn response template (guidance, not rigid format)

- “I have inherited and read the package; here is my understanding of the locked scope.”
- “These are the 3 most important technical uncertainties and the order I will test them.”
- “Here is the UX prototype approach and what I will show you first.”
- “I need [only truly necessary input] to run the first test.”
- “I will keep a persistent project status/decision record so future sessions can resume without rediscovery.”

## Handoff acceptance checklist

- [ ] Read all nine documents.
- [ ] Explicitly recognized cloud/multiuser architecture as **superseded**.
- [ ] Explicitly recognized Windows + macOS.
- [ ] Explicitly recognized no invented dialogue and natural conversational editing.
- [ ] Explicitly recognized user-provided assets and flexible interactive sound design.
- [ ] Explicitly recognized local preview/approve/commit and full-episode review.
- [ ] Explicitly recognized 1–2h target, 3h ceiling and near-zero manual micro-editing.
- [ ] Explicitly recognized Claude personal-plan integration as **unverified**.
- [ ] Created persistent status/decision docs and a next-action plan.
