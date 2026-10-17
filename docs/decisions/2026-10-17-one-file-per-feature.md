# Each feature writes its own files; shared registries are discovered, not edited

- Date: 2026-10-17
- Status: Claude 技术决策 (Leon asked how to stop the merge-conflict → re-run CI loop between parallel threads)
- Supersedes / changes: the append-only numbering of `docs/DECISIONS.md` (frozen at D50); `docs/PROJECT_STATUS.md` as the per-session log

Data (PRs #1–#39 on main): `docs/PROJECT_STATUS.md` was changed by 24 of 36 PRs, `docs/DECISIONS.md` by 16,
`docs/ROADMAP.md` by 14, `web/src/styles.css` and `web/src/api.ts` by 11, `lacuna_app/server.py` by 10,
`tests/app/serve_e2e.py` by 9, `web/src/App.tsx` by 8, `tests/app/fake_claude.py` by 6. Nearly every feature
appended to the end of the same files, which is exactly where git reports a conflict; a conflicted PR runs no CI.
The D-numbers collided twice (D49 cover vs packaging, D50 credit note vs packaging; #37 was closed and reopened over it).

Now a feature adds files instead of editing shared ones:
- Backend routes: `lacuna_app/routes/<feature>.py` with `register(app, ctx)`, discovered automatically
  (`server.py` keeps only the app context, the error handler and the static UI). Services are passed to
  `create_app(**services)` by name and built on demand with `ctx.provide(name, factory)`.
- Web: `web/src/features/<feature>/index.tsx` exports `feature` (episode tabs, pages, top-bar links), found via
  `import.meta.glob`; the feature's API calls and types in its `api.ts`, its styles in its own `.css`.
  `App.tsx`, `api.ts` and `styles.css` keep only the core (listen, review, chat, export, import).
- E2E servers: each feature's fakes in `tests/app/e2e/<feature>.py` (`configure(mode, ws, svc)`).
- Docs: one status file per phase in `docs/status/`, one decision per file in `docs/decisions/`;
  `ROADMAP.md` is the plan only, `PROJECT_STATUS.md` an index.
- Working rules for threads: `docs/PARALLEL_WORK.md`.
