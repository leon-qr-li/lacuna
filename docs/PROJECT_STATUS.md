# LACUNA Studio — Project Status

POC passed (Leon, 2026-10-17). The app is built in small phases per `docs/ROADMAP.md` (D34), several threads in parallel, released to Leon's PC in batches (project instructions).

**Where the state lives** (one file per phase or area, so parallel threads never edit the same file):
- `docs/status/phase-…md` — each phase: state, progress, how it is built, open issues. Its thread updates only its own file.
- `docs/status/foundation.md` — POC, AI first cut, Leon's PC setup, CI, cross-cutting open issues.
- `docs/status/voice-input.md` — chat voice input.
- Decisions: `docs/decisions/` (one file each, from 2026-10-17); D23–D51 in `docs/DECISIONS.md`.
- How parallel threads avoid merge conflicts: `docs/PARALLEL_WORK.md`.

Edit this file only when the overall picture changes (a new status file, a new kind of doc). Per-phase progress never goes here.
