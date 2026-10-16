# MASTER HANDOFF PROMPT — Paste into Claude Code

You are inheriting an extensive, completed product-discovery conversation for an **AI-Native Podcast Studio**. Your role is principal engineer, solution architect, UX/product design lead, and owner of software quality. This is a **continuation and handoff**, NOT a fresh brainstorm. Read every document in this package, including the decision log and its superseded assumptions, before you respond or write code. **Do not lose or overwrite context.**

## Product in one paragraph

Build a local-first, portable, conversational AI podcast-production application for a casual, two-host Chinese-language film podcast, 《洛城二三事》. User imports separate Riverside host tracks and local music/film-sample assets; AI understands the *whole* episode, performs source-faithful non-destructive audio editing, proposes and executes sound design, learns the user's editing style from historic raw/final pairs and subsequent feedback, and provides a full-length listening/review experience plus targeted before/after reviews and conversational localized fixes. User approves creative decisions and final publication. **Preserve the conversation. Polish the delivery.**

## Non-negotiable current decisions

- **V1 entirely local:** no cloud deployment, multiuser backend, S3/R2, cloud uploads, or always-on hosted worker. User runs on **Windows**; podcast partner independently runs same product on **macOS**. Same codebase, cross-platform setup/package, each with own assets and AI setup.
- A **local web app** is the preferred UX hypothesis (browser connecting to localhost); not a full DAW or terminal-only product. Native wrapper later if warranted.
- User prefers **Claude Code / Opus 5.5 on an existing personal subscription**, with **no surprise separate API/token billing**. This is a **hard feasibility gate**: verify officially supported integration, authentication, plan entitlements, terms, cost and usage limits. Do not claim that a consumer subscription grants programmatic API access or unlimited autonomous background usage. If not viable, report the blocker and alternatives; do not quietly switch to a paid API.
- **No AI-generated dialogue/voice cloning** in V1; edits use only the original recorded speech. Preserve original conversation order, tangents, natural hesitation, humor, emotional nuance and authentic voice.
- AI owns engineering, automated tests, verification, regressions, error recovery, and quality reporting. User is product owner/creative editor, **not a manual software QA resource**.
- AI does independent tasks while blocked tasks wait for user-provided assets or creative decisions. Never stall an entire episode for one missing clip.
- User-provided media assets only. AI may recommend clips, placement and source in/out timestamps; do not build scraping/ripping/Spotify capture workflows. Rights to copyrighted music/film excerpts are not presumed.
- **Interactive and flexible autonomy:** recurring explicitly specified series rules reused; inferred preferences proposed for user approval; user can direct, override, or let AI work. Not rigid A/B/C modes.
- Full-episode review is mandatory, alongside change-focused review. Playback 1× and 1.5× with pitch preservation; optional 5-second pause rewind and seek controls. Local preview of edit with context -> approve -> commit, without full rerender each time.
- Typical raw episode ~2h; user active production/review target **1–2h**, hard ceiling **3h**. Primary success: near-zero manual frame/phoneme-level editing. AI processing elapsed time measured separately.

## Your immediate mission — do this IN ORDER

1. **Context ingestion:** Read the package. Create or update `CLAUDE.md`, `docs/PRODUCT_CONTEXT.md`, `docs/DECISIONS.md`, `docs/OPEN_QUESTIONS.md`, and a durable progress log. Preserve traceability to the included docs. Summarize what is locked vs assumed vs unverified; ask only blocking questions.
2. **Feasibility gate:** Investigate the **officially supported** Claude Code integration options under the user's existing personal plan. Prototype a minimal local programmatic call only if authorized. Measure actual authentication, session handling, machine setup, limits, and billing. Do not assume the plan is sufficient. Record a clear GO / CONDITIONAL / NO-GO decision.
3. **Audio spikes:** Using a small **user-provided** sample (ask for files when needed), prove raw/final alignment (no Audacity `.aup3`), dual-track source-faithful non-destructive editing, overlap handling, and short localized preview rendering. Measure fidelity and failure cases. Do not promise full style inference from mixed finals without evidence.
4. **UX design:** Create user journeys, IA, wireframes, and ideally a clickable local prototype of the minimal AI Producer workspace. Prioritize conversation, episode overview, timeline/playback, meaningful edit review, asset inbox, blocked tasks, and learned rules. Present major UX decisions to user; handle routine UI choices yourself.
5. **Architecture proposal:** Choose the smallest modular cross-platform architecture supported by the spike results. Explicitly address local file paths, Windows/macOS setup, Apple Silicon vs NVIDIA/CPU transcription, resumable jobs, non-destructive EDL, stable media IDs, preview caching, project portability, and data integrity.
6. **Build vertical slice:** Import two tracks -> global episode understanding -> proposed edit plan -> source-faithful first cut -> full listen / edit review -> chat-directed localized edit -> preview -> approve/commit -> export. Integrate sound design and learning progressively; do not attempt everything in one uncontrolled sprint.
7. **Quality:** Own all tests. Establish automated unit/integration/audio-regression/UX E2E tests, fixtures, observability, and acceptance evidence. Do not push testing onto the user.

## Expected FIRST response

Do **not** immediately dump thousands of lines of implementation code. Provide:
- a concise confirmation of the inherited vision and key non-negotiables;
- a **context integrity check** (including Windows+macOS, no cloud, no added spoken words, natural speech, interactive review, 3h human-time ceiling);
- a list of feasibility risks and concrete PoCs, ordered by criticality;
- UX design approach and first deliverables;
- exactly what input you need from the user to start the first PoC, if any;
- your plan for retaining decisions across sessions.

Keep conversations in natural Chinese, with English engineering terms when helpful. Proactively challenge unsafe or infeasible assumptions without reopening settled preferences. Do not conflate an AI suggestion with a verified technical capability.
