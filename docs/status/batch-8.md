# Batch 8: code freeze + full regression

Thread 「第八批：代码冻结与全面回归」 (2026-10-25). No new features from here on; bug fixes only.

## State (2026-10-25)
- Regression case list (333 cases, 30 groups, results per case for Claude and Leon, saved in the page's
  `results` db collection): https://claude.ai/artifact/GPtn1TkZHGzoy8tEqnd4Gg
- Runs: pytest 871 passed / 17 skipped (real-model ASR tests skip without `LACUNA_ASR_MODELS`); E2E 150
  passed (the tour test passed on its retry). Every case was mapped to the tests that check it; security,
  edge-case and visual sweeps ran on local servers (the live site is behind Cloudflare Access and needs
  Leon's sign-in, so Claude can't walk it).
- E2E locally: this container's Chromium is newer than the pinned Playwright's; run with a local config that
  sets `executablePath: "/opt/pw-browsers/chromium"` (kept out of git).

## Fix PR 1 (no security changes)
- 封面 in the cloud showed a server folder path and 「打开文件夹」, and a show without 喜马拉雅 had no way to
  download the chosen cover: now a 「下载封面」 link (and 上传喜马拉雅 no longer shows server paths).
- A 0-second track is refused at import with a plain message (was a raw numpy error after upload).
- Odd upload names (`....wav`, 400 characters) answered 500: 422, or the name is cut by bytes keeping `.wav`.
- An episode left with only `state.json.bak` (crash between the two renames) disappeared, its id could be
  reused and its uploaded recordings pruned: it now counts as an episode (`Workspace.episode_ids`).
- Missing recordings: export and the music mix answer the same clear 409 as listening, before anything starts.
- 移出素材库 of a file an episode's music plays asks again, naming the episodes (409 + `force`).
- Episode ids with invisible characters are refused at import.
- The session-expired sign-in screen says 「登录已过期，请重新登录。」 (not after 退出登录).
- The quota refusal names the real button 「想要更多时长」; a stray space in the terms; admin demo data uses
  example.com addresses only.

## Waiting on Leon (security changes need his typed words)
See the final report. Found by the security probe: password-reset code guessing has no cooldown after 5 wrong
tries; `GET /api/app` lists other shows' running jobs and the server path; a non-owner site admin can end the
owner's sessions in the admin; the main site sends no nosniff / frame headers.

## Next action
Merge PR 1 → deploy; visual walkthrough findings → PR 2; final report.
