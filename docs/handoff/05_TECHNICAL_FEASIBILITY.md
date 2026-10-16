# Technical Feasibility, Architecture Hypotheses and Risks

## Gate 0 — Claude Code / Opus 5.5 subscription integration (CRITICAL)

The user has chosen **Claude Code + Opus 5.5** (not an alternative premium model) and prefers using an existing **personal plan**, with **no separate metered Anthropic API billing**. A local web app cannot be assumed to drive an arbitrary long-running Claude Code session under consumer subscription terms. Investigate **current official documentation** and experimentally validate only a supported method. Confirm:

- Is local programmatic invocation from the app supported under the user's plan and terms? Which CLI/SDK invocation modes and auth pathways are permitted?
- Does this trigger metered API billing? How can user detect and prevent unexpected charges?
- Session persistence and resumption, structured JSON output, streaming, timeout/cancellation, tool permission boundaries and rate/usage limits.
- Compatibility on Windows and macOS; CLI installation and authentication UX.
- Whether long-running background work is allowed/reliable; fallbacks when auth/limits expire.
- **No credential scraping, hidden session hijacking, token reuse hacks or unauthorized automation.**

**Exit criterion:** documented GO / CONDITIONAL / NO-GO with real test evidence. If NO-GO, do not silently introduce paid API; present tradeoffs to user for a decision.

## Gate 1 — Raw/final alignment

Input: user-provided raw dual tracks and mixed final. No `.aup3` editing projects. Final may contain soundtrack, crossfades, loudness changes, clips, speed changes and edits. Candidate approach: ASR transcripts with timestamps, forced alignment, acoustic fingerprints, cross-correlation/DTW for ambiguous spans, music/speech segmentation. Label uncertain alignments. Measure how accurately cuts and moves can be reconstructed and where motive cannot be inferred.

## Gate 2 — Non-destructive dual-track editing

Represent original immutable audio references plus time-range operations (cuts, trims, slips, crossfades, gains, ducking, clip inserts) in a versioned EDL/timeline. Render via FFmpeg or suitable DSP pipeline. Validate:

- sample-accurate boundaries and sample-rate conversion;
- track synchronization, drift, overlaps and interruption semantics;
- seam quality (clicks, unnatural breath/room-tone gaps), clipping, peak/loudness, true peak if mastering;
- source provenance and reversible decisions;
- local preview with context and cache invalidation when upstream timing changes;
- version/undo, crash-safe writes and deterministic rerenders.

## Gate 3 — Global understanding and speech editing

- Whole-episode semantic analysis before editorial choices, then topic-based segmentation and context-aware edits.
- Candidate local tools: FFmpeg, Python, faster-whisper or comparable ASR, VAD, forced alignment, SQLite; choose based on measured performance and platform support, not hype.
- Windows CPU/NVIDIA and macOS Apple Silicon/CPU differ. Avoid assuming CUDA works on Mac or a single faster-whisper acceleration backend works everywhere. Make fallback explicit.
- Spoken-word accuracy and bilingual proper nouns, film titles, code-switching, laughs and overlapping speech are challenging. Track confidence and allow correction.

## Architecture hypothesis — NOT a locked stack

Local web UI (localhost only) -> local backend/orchestrator -> task/dependency engine -> AI editorial adapter (officially supported Claude integration if feasible) -> audio processing engine -> versioned local EDL/projects -> local workspace, cache, metadata DB. Use structured messages, stable IDs, job state persistence and task retries. A native wrapper (e.g., Tauri) is optional later, not necessary for V1.

**Local workspace**: configurable folder; suggested subfolders for raw, historic references, assets, episode inbox, projects, exports and cache. Do not hardcode platform-specific paths; use `pathlib`/equivalent. App code and user data must remain logically separated. Avoid including large copyrighted media in distributable code package.

**Packaging**: one codebase, platform-specific setup/install scripts or bundles. Windows and macOS smoke tests; detect installed dependencies, Apple Silicon/Intel, CPU/GPU, permissions, disk space. If partner lacks Claude access, warn and disable AI-dependent actions; do not claim exact plan detection without a supported signal.

## Task engine and resilience

- Jobs form a dependency graph. Missing asset blocks only its dependents; other tasks continue.
- Persist status and progress across restart. Make tasks idempotent; guard duplicate render/commit/publish actions.
- Watch local folders with debounce and stable-file checks; prevent reading partially copied audio.
- Never delete raw files. Use content hashes/stable media IDs, atomic project writes, migrations, backups and safe export paths.
- No localhost service exposure to public internet; protect against path traversal, command injection via file names/prompts, malicious media and unsafe shell commands.

## Media rights and publishing caveats

- User may discover film scores via Spotify, but Spotify access does **not** grant permission or a usable MP3 download. AI asks for user-provided files, never instructs illegal ripping.
- Film clips and music may require rights clearance; preserve source metadata and avoid automated distribution claims.
- 喜马拉雅 open platform appears to advertise audio upload capability, but individual-account eligibility and supported API integration are **unverified**. Browser automation may be technically possible but must be tested for robustness and platform permission. V1 fallback is assisted manual upload.

## PoC artifacts and measurements

- Short, reproducible demo; README for both OSes.
- CLI/AI bridge feasibility report with official-source links, actual observed cost/usage behavior and failures.
- 5–15 minute dual-track source -> EDL -> edited excerpt -> A/B preview -> undo demo.
- One historic raw/final sample alignment with error/confidence report.
- CPU/GPU processing times and memory usage on available hardware; no fabricated performance promises.
- Go/no-go architecture decision record before committing to full build.
