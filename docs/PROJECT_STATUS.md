# LACUNA Studio — Project Status

POC passed (Leon, 2026-10-17). The app is built in small phases per `docs/ROADMAP.md` (D34), several threads in parallel, released to Leon's PC in batches (project instructions; `docs/INSTALL.md` 更新).
Phases 1–11 (except 6b, cancelled) are done. Since 2026-10-18 the work comes from Leon's first full test, the 首次检测 backlog (`docs/status/ui-backlog.md`).

**Where the state lives** (one file per phase or area, so parallel threads never edit the same file):

| Area | Status file |
|---|---|
| POC, AI first cut, Leon's PC, CI, cross-cutting open issues | `docs/status/foundation.md` |
| Phases 1–11 (review, export, chat, import, learning, music, packaging, UI, publish pack, poster, 喜马拉雅 upload) | `docs/status/phase-01-review.md` … `phase-11-upload.md` |
| End-to-end rehearsal of a 2-hour import | `docs/status/rehearsal-e2e.md` |
| Chat voice input | `docs/status/voice-input.md` |
| Interface language (zh / en) | `docs/status/i18n.md` |
| Storage (JSON files, episode cache) | `docs/status/storage.md` |
| Sign-in | `docs/status/auth.md` |
| Logo, palette, loading indicator | `docs/status/brand.md`, `palette.md`, `loading.md` |
| Review shortcuts and progress | `docs/status/review-keys.md` |
| 首次检测 backlog (index of items 1–28) | `docs/status/ui-backlog.md` |
| Backlog areas: review + editing, volume, music page, show notes 喜马拉雅版, dialog + brand text | `docs/status/review-edit.md`, `levels.md`, `music-page.md`, `show-notes-ximalaya.md`, `dialog-brand.md` |

- Decisions: `docs/decisions/` (one file each, from 2026-10-17); D23–D51 in `docs/DECISIONS.md` (frozen); D01–D22 in `docs/handoff/07_DECISION_LOG.md`.
- How parallel threads avoid merge conflicts: `docs/PARALLEL_WORK.md`.

Edit this file only when the overall picture changes (a new status file, a new kind of doc). Per-phase progress never goes here.
