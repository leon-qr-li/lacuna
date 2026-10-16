# Product Requirements Document (PRD)

## Vision and audience

**Name (working):** AI-Native Podcast Studio. Primary user: creator/editor of 《洛城二三事》, a Chinese-language, two-host, naturally casual film podcast (including a 1990s retrospective series). Secondary user: co-host who may install and use a copy **independently on a Mac**; there is no shared account/workspace in V1.

**Core promise:** Eliminate tedious manual micro-editing while protecting conversational spontaneity. The user wants to say "开干", let an AI producer work, listen, correct with natural-language instructions, approve, and export/publish. This is not an objective to maximize compression, polish, or speech density.

## Existing manual workflow

1. Record two separate tracks on Riverside; typical raw length about two hours.
2. Download tracks and edit in Audacity, removing distracting stumbles, long dead air, rough overlaps, bad interruptions, rambling with no value, and adjusting levels.
3. Insert series-specific intro jingles, film soundtracks as transition music and low-volume underscore, film dialogue/trailer clips, and outro.
4. Mix, export, listen through, create show notes, chapters/timestamps, poster; upload to 喜马拉雅. 小宇宙 currently syndicates automatically from that publishing flow.
5. Manual effort typically 5–10h, occasionally ~20h. User routinely listens through entire finished episode (initially 1×, later prefers 1.5×).

## Success metrics

- For a typical ~2h raw episode, **human active production/review** 1–2h preferred, **never >3h** as acceptable target. Separate human active time from machine processing and forced waiting.
- Near-zero requirement to manipulate individual frames, phonemes or waveforms manually in Audacity.
- Source-faithful, natural, intelligible conversation and synchronized dual-track audio; user retains editorial agency.
- First-cut acceptance, edit-restore rates, missed critical defects, false deletions, audio seam artifacts, and rework time are useful diagnostics, not simplistic vanity metrics.
- Full-length playback and change-focused reviews both usable; review load manageable, no hundreds of approvals.

## Functional requirements

### Episode ingest and understanding
- Read episode assets from a **configurable local workspace**, not upload to a cloud service.
- Import separate host audio tracks, verify format, durations, clock alignment/drift, sample rates, channel mapping, and media integrity.
- Transcribe/align with speaker and timestamp references. Analyze the **entire episode first** to understand topics, running jokes, callbacks, themes, repetitions and shifts; semantic/topic segmentation for editorial review rather than arbitrary fixed 3/5-minute chunks.
- Produce episode summary, segments, risks, editorial opportunities and a non-destructive edit plan.

### Editing
- Clean distracting verbal stumbles, unintentionally bad repetitions, dead air, noise and volume imbalance **without flattening natural speech**.
- Preserve natural thinking aloud, hedges, repeated emphasis, laughter, humor, off-topic tangents, original chronological conversation order.
- Handle separate-track interruptions intelligently: keep valuable affirmations by moving the interruption later *within conversational sense*; delete disruptive interruptions and restore natural continuity on the co-host track when justified. Never invent words.
- Provide edit-level provenance: source file/time ranges, transformation, reason, confidence/uncertainty, reversibility.
- Support non-destructive timeline / EDL, undo/redo, alternate versions, short preview rendering and final mix/export.

### Interactive AI producer
- User may give per-episode creative direction before, during or after initial cut.
- AI should proactively suggest and execute routine low-risk edits, ask for high-impact creative decisions only as needed, and adapt autonomy per task/context; no single mandatory A/B/C mode.
- Missing assets create tasks and precise local inbox/folder instructions; other independent work continues. Auto-detect added files, normalize/index/tag, associate with project and resume dependent work.
- Preserve task states and dependencies; show what is done, in progress, waiting on user, and failed with recovery actions.
- Conversational edits resolve to current playhead/selected segment and episode context; ask only when ambiguous.

### Sound design
- User selects/provides film soundtrack files (often discovers recognizable cues via Spotify); **do not automatically scrape, rip, download or record them**.
- Famous/recognizable or atmosphere-defining theme is often used at **normal prominent transition/interlude level**; less famous atmospheric cues at **very low volume under speech**, with appropriate ducking/level control.
- User supplies locally captured film dialogue/trailer samples when inspired by a funny, thematic or quoted moment. AI may proactively propose *where/why* to insert a clip, but cannot assume the clip exists or that it has rights.
- Recommend music source in/out timestamps **after listening/analyzing actual supplied asset**, not fabricated timestamps. If no file yet, request it and describe the desired emotional function without inventing a precise excerpt.
- Reuse user-defined series jingles and intro/outro conventions. Record metadata and provenance automatically; user should not manually tag and catalog assets.

### Style learning and memory
- User has about **10 recent historic episodes**, each potentially with raw Riverside two-track audio and mixed final episode (~30 audio files total); availability of older files uncertain; **no Audacity project files**.
- Infer observed cuts/moves from mixed finals using transcription and acoustic alignment; do not claim to know the user's motivation from final output alone.
- Start with 1–2 paired episodes as feasibility samples, then use more data with held-out validation; preserve evidence and uncertainty.
- Memory levels: (a) one-episode decisions, (b) inferred candidate preferences with supporting examples and confidence, (c) approved durable rules with episode/series/global scope. Explicit user instructions can be recorded as active rules; inferred rules require user approval before promotion.
- Present a compact periodic candidate-rule review rather than interrupting constantly. Support rule editing, rollback and precedence.

### Review UX
- First-class full-length continuous listening, and an edit-focused view with consequential changes, reasons, before/after snippets, restore controls and direct navigation.
- Playback speed **1× and 1.5×**, pitch-preserving, retaining position; optional auto-rewind 5s on pause plus manual seek controls.
- Pause, give feedback in chat tied to playhead, AI makes a local edit and previews a contextual excerpt; **approve then commit** to timeline, avoiding whole-episode rerender on every small change.
- Full episode and edit review share timeline, playhead, comments, history, and approved versions.

### Outputs and publishing
- Final mastered audio; metadata package including title suggestions, episode summary, show notes, chapter timestamps, cover/artwork assets if requested/available, and upload checklist.
- 喜马拉雅: assisted publishing is the safe V1 baseline; investigate official upload API entitlement and permitted browser automation via Playwright separately. Do not assert automated publishing is supported until tested. Require explicit human approval before any publish action.
- 小宇宙 syndication is an existing user workflow, not evidence of guaranteed API/sync timing. Treat `exported`, `uploaded`, `published`, `syndicated` as distinct states; verify rather than assume.

## V1 boundaries / non-goals

- No cloud backend, R2/S3, online upload, remote shared account, or always-on worker.
- No collaborative realtime editing, shared cloud library, remote job processing, or browser accessible over public internet.
- No full DAW replacement or mandatory micro-waveform editing UI.
- No generative synthetic dialogue, impersonation, transcript rewriting or changing the words actually spoken.
- No unlicensed media acquisition pipeline, automatic copyrighted media downloading, or rights guarantees.
- No commitment to fully automated 喜马拉雅 publishing in the first vertical slice.
- No requirement for exact AI-to-human edit equality; different natural edits may be valid.

## Packaging and portability

- Single codebase for **Windows user + macOS partner**; each installs and runs locally with own configured folder and own AI authentication/plan.
- Setup checks OS, dependencies, audio processing capability, Claude Code installation/auth/integration readiness; display actionable warnings and disable unavailable AI functions gracefully.
- Cannot reliably infer exact Claude plan solely from installed binary; verify operational eligibility rather than saying "you have no personal plan".
- Source code, project data, cache and personal media logically separated to survive updates and enable safe backup/portability.
