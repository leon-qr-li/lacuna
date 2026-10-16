# Decision Log — authoritative product history

This log preserves important corrections and **superseded ideas** to prevent loss of context. `CONFIRMED` means user explicitly agreed; `PROPOSED` means assistant suggestion requiring verification/implementation judgment.

| ID | Decision | Status | Notes |
|---|---|---|---|
| D01 | Primary AI preference Claude Code with Opus 5.5 and existing personal subscription; avoid separate API charges | CONFIRMED preference / integration UNVERIFIED | Do not assume subscription supports arbitrary app automation. |
| D02 | Local-first V1, no cloud deployment/storage/uploads or shared web app | CONFIRMED | **Supersedes** earlier hosted multiuser/R2/S3 plan. |
| D03 | Creator Windows; partner macOS; independent local installs, same codebase | CONFIRMED | **Supersedes** mistaken statement both Windows. |
| D04 | Configurable fixed local media folder, portable setup and project packaging | CONFIRMED | User wants to hand package to partner; partner has own AI setup. |
| D05 | Local Web App UI preferred, not CLI-only or full DAW | CONFIRMED direction | Exact frontend stack not decided. |
| D06 | Preserve original conversation order and natural tangents | CONFIRMED | No wholesale content restructuring. |
| D07 | Natural speech > polished speech; remove distracting awkward stumbles, not conversational personality | CONFIRMED | User corrected assistant's too-concise examples. |
| D08 | No invented words/AI voice generation | CONFIRMED | User explicitly flagged “还是/可能” not present in source. |
| D09 | Two separate Riverside tracks; intelligent interjection movement/deletion and co-host continuity repair | CONFIRMED | Core differentiator. |
| D10 | Analyze full episode before local edits; topic-based segmentation | CONFIRMED | Context and callbacks matter. |
| D11 | First-cut/edit-first, then contextual review and iterative conversation | CONFIRMED | No requirement to approve every micro edit before first draft. |
| D12 | Sound design autonomy flexible per task, not fixed A/B/C | CONFIRMED | AI learns series jingles, suggests, inserts provided assets. |
| D13 | User supplies music, film dialogue/trailer clips; AI owns local folders, indexing, metadata, editing/mixing | CONFIRMED | AI can suggest cue and source range once asset exists. |
| D14 | AI continues independent work while waiting for missing assets/creative decisions | CONFIRMED | Task-level dependency management. |
| D15 | Full-length listen and edit-focused review both mandatory | CONFIRMED | Shared playhead/context. |
| D16 | Pause/chat -> local contextual preview -> approve -> commit; avoid full rerender per fix | CONFIRMED | Non-destructive edits and undo. |
| D17 | Proactive inference of preferences; inferred durable rules need user approval | CONFIRMED | Episode/series/global scope; batch candidate reviews. |
| D18 | 1–2h human active time target; 3h ceiling; eliminate manual micro-editing | CONFIRMED | Machine processing time separate. |
| D19 | 1× and 1.5× playback; optional 5-second rewind | CONFIRMED | Routine UX details should be owned by builder. |
| D20 | 喜马拉雅 assisted upload baseline; official API and browser automation TBD | PROPOSED / technical status UNVERIFIED | No automatic publish promise; 小宇宙 syndication not automatically verifiable. |
| D21 | Product discovery sufficiently complete; hand off to Claude Code for feasibility, UX design, implementation | CONFIRMED | Do not ask user to repeat decisions. |
| D22 | Engineering QA/testing responsibility belongs to implementation agent, not creator | CONFIRMED | User gives editorial approval, not software QA labor. |

## History of important pivots

1. Initial ambition included cloud-hosted shared UI, shared library, S3/R2, remote uploads and local worker; user **explicitly rejected this for V1** because of local AI session concerns and complexity.
2. Assistant briefly planned Windows-only installers based on a mistaken user answer; user corrected that partner uses **Mac**. Cross-platform support is now required.
3. Assistant initially framed sound design autonomy as exclusive A/B/C choices; user rejected rigidity. AI should be interactive, adaptive, proactive and learn from explicit instructions.
4. Assistant proposed too polished/concise speech rewrites and even added words; user strongly corrected: preserve colloquial natural speech, no new words.
5. Assistant asked too many trivial UX questions; user challenged that. Builder should independently decide routine player controls, testing and engineering details.

## Open / deliberately deferred

- Exact supported Claude Code personal-plan app integration; critical blocker if infeasible.
- Exact cross-platform packaging and runtime stack; select after PoCs.
- Performance on actual Windows/Mac hardware; need benchmarks.
- Detailed asset rights/clearance, official 喜马拉雅 API eligibility and any permitted Playwright automation.
- Precise criteria for automatically applying high-impact content edits; refine with real examples and review evidence.
- Actual historic files and specific samples to use for evaluation; ask for them when technical work requires them.
- Poster generation/cover design details and final publishing automation; later phase.

## Communication contract

User wants Claude Code to **drive** engineering, design, tests and normal UX decisions. Ask one meaningful question at a time only when a genuine product tradeoff or blocker remains. No generic re-discovery, no endless multiple-choice questions, no empty progress narration. Use evidence, demos and explicit go/no-go gates.
