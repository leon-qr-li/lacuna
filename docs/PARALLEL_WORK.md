# Working in parallel threads without merge conflicts

Several Claude threads build features at the same time. A PR that conflicts with main runs **no CI** and
cannot merge, so every conflict costs a fix plus a full CI run. These rules keep conflicts rare.

## Where a feature puts its code
| Kind | Put it in | Do not add it to |
|---|---|---|
| API routes | new `lacuna_app/routes/<feature>.py` with `register(app, ctx)` (auto-discovered) | `lacuna_app/server.py` |
| Service a route needs | `ctx.provide("<name>", lambda: Service(ctx.ws))`; tests pass a fake as `create_app(..., <name>=fake)` | new `create_app` parameters |
| New Python subpackage | also list it in `[tool.setuptools] packages` in `pyproject.toml` (a test checks) | — |
| Web page / episode tab / top-bar link | new `web/src/features/<feature>/index.tsx` exporting `feature` | `web/src/App.tsx` |
| Web API calls + types | `web/src/features/<feature>/api.ts` | `web/src/api.ts` (core only) |
| Styles | `web/src/features/<feature>/<feature>.css`, imported by its `index.tsx` | `web/src/styles.css` (core only) |
| Interface text | Chinese wrapped in `t("中文")` (`web/src/i18n`), English in `web/src/features/<feature>/en.ts`; `npm run build` fails on bare Chinese or missing English | `web/src/i18n/en.ts` (shell + shared components only) |
| Episode flow step | a tab in the feature's `index.tsx` with an `order` (built in: 审阅改动, 整集试听; then 声音 15, 本集学到的规则 20, 配乐 30, 导出 35, 发布 group 40–60) | `web/src/App.tsx` |
| Confirm / notice popups | `confirmDialog` / `noticeDialog` from `web/src/features/dialog/Dialog.tsx` | the browser's `confirm` / `alert` / `prompt` (build fails) |
| User-visible AI name | "LACUNA" (`i18n.AI_NAME_RULE` at the end of prompts whose output Leon reads) | "Claude" / "Anthropic" in any interface text (build, `tests/test_brand_text.py`, E2E fail) |
| E2E server fakes | new `tests/app/e2e/<feature>.py` with `configure(mode, ws, svc)` | `tests/app/serve_e2e.py` |
| Fake Claude for a feature | a new file under `tests/app/` (e.g. `fake_<feature>.py`) | the end of `tests/app/fake_claude.py` |
| Progress, build notes, open issues | the phase's own `docs/status/phase-…md` | `docs/PROJECT_STATUS.md`, `docs/ROADMAP.md` |
| A decision | new `docs/decisions/<date>-<slug>.md` (no number) | `docs/DECISIONS.md` (frozen) |

Changing core code (episode, review, chat, export, import, the engine) is fine; just keep the change to what the feature needs.

## Git routine for a thread
1. Start the branch from the latest main.
2. Before opening the PR: `git fetch origin main && git merge origin/main`, run the checks, push.
3. After opening (and after every push): check the PR is mergeable and that a CI run started. A conflicted PR shows no CI at all.
4. When GitHub reports a conflict (or a "base branch recovered" notice): merge main into the branch right away (never rebase a pushed branch), resolve, run the checks, push.
5. No need to merge main just because main moved: if the PR is mergeable and "CI ok" is green, merge it.
6. Keep PRs small and merge them as soon as they are green; split a big feature into several PRs rather than one long-lived branch. Docs-only PRs (status, validation notes) skip CI and merge in seconds.
7. If you must edit a file another open PR is also changing, tell that thread first (via the coordinator) and agree who merges first.
