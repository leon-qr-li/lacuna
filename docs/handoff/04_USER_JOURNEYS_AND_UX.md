# User Journeys and UX Design Brief

## UX north star

**An AI producer workspace, not a DAW clone.** The user wants to be lazy about technical editing, not passive about creativity. Design for chat-first direction, meaningful audio previews, task visibility and effortless asset handling. Preserve full control and reversibility without forcing waveform micro-manipulation.

## Journey 0 — First-time setup (Windows or macOS)

1. Install or start local app; select/configure a persistent local workspace directory.
2. Setup checks OS, Python/runtime or bundled binaries, FFmpeg, transcription engine, Claude Code integration and operational auth readiness, media storage permissions, available disk space, CPU/GPU/Apple Silicon capability.
3. Show actionable `Ready`, `Needs setup`, `Unavailable`, `Limited mode` states, not vague errors. Partner on macOS may lack a compatible Claude subscription: show warning, supported setup instructions and what works without AI.
4. Open browser to localhost; bind only to loopback by default; no public exposure.
5. Keep personal assets/data separate from installed app binaries; support upgrades without data loss.

## Journey 1 — First episode import and kickoff

1. User puts Riverside host tracks into configured folder; app detects or lets user choose episode.
2. AI validates tracks, offers title/series identification and asks only material creative setup questions.
3. AI scans full episode, summarizes topics, callbacks, pacing, risk spots and planned edits.
4. For 1990s series, reuse previously approved intro jingle; if none yet, ask user to specify and save series rule.
5. AI creates an episode-specific asset inbox and says plainly which music/clip is missing. Continue voice editing while waiting.
6. User says “开干”; AI produces first cut and a manageable review summary.

## Journey 2 — Proactive music collaboration

1. AI recognizes movie/topic and suggests a prominent theme for transition and quiet atmospheric underscore.
2. If file is not in local library, AI requests a **user-provided** audio file in an auto-created folder; don't claim a Spotify link is downloadable media.
3. After file appears, AI analyzes waveform, duration, emotional fit, candidate source in/out ranges and mix plan.
4. AI previews proposed transition/underscoring and applies/adjusts per user direction; no need for user to manually fill tags.
5. User-provided dialogue/trailer clips are similar, but AI primarily suggests *creative opportunity* and waits for actual clip.

## Journey 3 — First cut review

Two complementary modes sharing playhead/context:

**Full Listen:** continuous start-to-finish playback of final-like mix. 1× and 1.5× pitch-preserving speed options; pause, seek, optional 5-second auto-rewind, quick comments, chapter markers, keyboard shortcuts, resume position. This is **mandatory**: user always listens through the finished episode.

**Edit Review:** navigation to consequential edits with reason, original/edited audio A/B, context, restore and chat revision. Summarize mechanical edits in groups; avoid 100+ approvals. Highlight risky content cuts and track-overlap changes.

## Journey 4 — Conversational local fix

1. User pauses at e.g. minute 42 and says “这块不太对，把前面那句恢复一下，然后停顿短一点”.
2. AI resolves current playhead and contextual utterance; asks clarification only if ambiguous.
3. Modify non-destructive edit plan and render a **short excerpt with pre/post context**; do not rerender the whole 95-minute episode.
4. User previews A/B, approves or iterates; **approve -> commit** to episode timeline.
5. Undo and compare any time; record feedback as episode decision and possibly evidence for candidate preference.

## Journey 5 — Learning from historic examples

1. User provides pairs of Riverside raw two tracks + personally edited final mixed output; ~10 recent episodes available, older uncertain, no Audacity project files.
2. AI aligns, identifies **observable** retained/deleted/moved passages, mix/music, uncertainty, and possible preference patterns.
3. Present small interpretable sample observations and let user correct misinterpretations.
4. Hold out episodes for evaluation; only after repeated evidence suggest persistent rules, with user approval.

## Journey 6 — Export/publishing

1. User approves mix. Render full audio, metadata, chapters/show notes and publishing assets.
2. Provide assisted 喜马拉雅 upload bundle with prefilled/copyable information and an open-upload-page action where feasible.
3. Investigate supported official API and allowed browser automation later; do not publish without explicit human approval.
4. Track exported, uploaded, published and 小宇宙-syndicated states separately; never imply syndication confirmed without evidence.

## Suggested information architecture

- **Home / Episodes:** list, status, import, start/resume.
- **Episode Workspace:** primary player/timeline, chat, summary, tasks, sound design suggestions.
- **Review:** Full Listen / Edit Review tabs or toggle; shared playback position and history.
- **Asset Inbox / Library:** local watched folders, missing asset requests, file health and automatic metadata.
- **Editing Playbook:** global/series rules, candidate rules pending approval, examples, change history.
- **Settings / Diagnostics:** workspace location, audio backend, Claude auth/readiness, model usage/cost warnings, system health.

## Design principles and failure states

- Keep UI minimal, friendly and creative, not engineering-heavy. Waveforms and EDL are available as supporting detail, not the main task.
- Clear task states: queued, running, waiting for asset, waiting for decision, ready for review, failed/retry, complete.
- Preserve progress across app restarts, crashes and asset changes; never silently discard approved edits.
- Support offline operation; user data remains local.
- If AI unavailable, explain why and what offline non-AI capabilities still work. Never invent plan entitlement checks.
- If an edit has low confidence, preserve source, mark uncertainty and offer review; don't silently damage conversation.
- Responsive desktop-first UX for Windows/macOS; accessibility, keyboard navigation and screen-reader labels as sensible defaults.

## UX deliverables requested from Claude

1. Journey map and information architecture.
2. Low-fidelity wireframes for Setup, Episode Workspace, Full Listen, Edit Review, Asset Inbox, Learning Rules.
3. Clickable local prototype showing a realistic two-host episode and interactions; mock data clearly labeled.
4. Usability walkthrough and rationale focused on reducing human time and approval fatigue.
5. Design tokens/component plan, only after core flows validated.

## Important: routine choices are YOUR responsibility

Do not keep asking the user about trivial buttons, 5-second skip behavior, basic layout or standard player controls. Ask about genuine editorial intent, important workflow tradeoffs or blocking constraints.
