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

## Fix PR 2 (visual walkthrough)
A cloud-mode server walked in zh/en × dark/light × 1440/1024/390 (about 1,600 screenshots), every fix re-shot:
- 封面 could still show the server folder when one `/api/auth/status` call failed (`useCloud` took a failure as
  "not cloud" for the whole page load): a failed call is asked again.
- Admin: 告警邮件 table ran out of its card in English; CPU/memory axes read "PM PM PM" (now 24-hour, fewer ticks);
  「系统正常」 while no backup was ever recorded (cloud now warns); raw show role "admin"; audit details in field names;
  feedback detail header squeezed; the reply box clipped 回复 at 1024 (grid rows now keep their content's height);
  本机 → 这台设备; "Member" header; the phone top bar's cut-off title.
- Main site: 收起 covered the 这附近改了什么 count at 1024; toast 撤销 broke onto two lines; tour pill covered the title
  (moves to the bottom under 1180px); role table headers one character per line and 音量 vertical on phones; the dB
  value ran out of the card; poster hint cut off; error page without a side gutter; dangling › in the step tabs;
  English plurals; 已生效 rules said "If adopted"; 电脑 / App wording.
Left as noted (not bugs or not for the freeze): review titles stay in the language of the first cut; legal TBD
placeholders wait for the lawyer; the 401 of `/api/site/notice` before sign-in in the browser console.

## Fix PR 3 (Leon's picks on the decisions page, 2026-10-26: all A; "都选完了，做")
- S1 reset codes: 5 a day per email, none for an hour after one is burnt, 20 requests an hour per address
  (decision 2026-10-26-batch8-security-fixes).
- S2 `GET /api/app` from the browser on the shared server: no busy list, no server folder (the host's updater on
  loopback still gets both).
- S3 a site admin can't end the owner's (or another admin's) sessions; the admin's user drawer hides the buttons
  the server would refuse.
- S4 main site: nosniff, X-Frame-Options DENY + `frame-ancestors 'none'`, Referrer-Policy.
- S5 feedback screenshots must decode as the PNG/JPEG they claim (Pillow).
- S6 one cloud-mode test, `cloud.enabled()` (1 / true / yes), used by sign-in and admin alerts too.
- S7 kept as is (disabled accounts get 「邮箱或密码不对」).
- P1 already in place: 节目设置 → 主持人 says 「改名字不影响已经导入的剧集；新导入的剧集用新名字。」
- P2 只听 members: 「只听成员」 tag next to the show name (like 已归档 · 只读); review, chat, nearby/timeline restore and
  export buttons greyed out (feature folder `web/src/features/listen-only/`).
- P3 `uptime.yml`: hourly `/api/health` through Access with the deploy token; 3 tries a minute apart; a failed run
  mails the repo owner.
- New (Leon 2026-10-26, design C 「权限对照卡」 picked from three on the canvas
  https://claude.ai/artifact/SW5utkSCodq3QpnEESposu): making someone a site admin mails them what the role allows and
  the admin's and the site's links (`lacuna_app/admin_invite_mail.py`). Leon keeps a single owner (asked about two;
  decided against it).

## Waiting on Leon (security changes need his typed words)
See the final report. Found by the security probe: password-reset code guessing has no cooldown after 5 wrong
tries; `GET /api/app` lists other shows' running jobs and the server path; a non-owner site admin can end the
owner's sessions in the admin; the main site sends no nosniff / frame headers.

Decisions page (S1–S7 security, needs his typed words; P1–P3 product): https://claude.ai/artifact/VUiqsSf8CHmd5fb9U12h4t

## Next action
Merge PR 3 → deploy. Then Leon's week of testing from the case page.
