# Second full scan (2026-10-18, batch V1–V10)

Thread「第二批横扫」. After Leon's validation fixes merged (#109–#115: V1–V3, V5, V6, V7, V8, V9, V10; V4
won't change), ran the whole suite on main (pytest + all E2E, locally and a full three-OS CI run) and
walked the new features through real use together: 配乐 page speed + library scopes, music page upload,
AI error messages, room tone repair + clipping repair on episode open, 喜马拉雅 default style.
Acceptance checklist for Leon: `/mnt/project-files/lacuna/docs/验收_2026-10-18/11_第二批验收清单.md`.

## Fixed
| Area | Bug | Test |
|---|---|---|
| 配乐 page (V10) | With only other episodes' files in the library the page said 「素材库里还没有音乐」 | `web/e2e/sweep2.spec.ts` |
| 配乐 page (V10) | A file added with 「从电脑添加」 wasn't picked in 放一段音乐 (the first one stayed selected) | same |
| 配乐 page (V10) | Adding a file the library already had as shared said 「已加到这一集」 | same |
| 喜马拉雅版 (V9) | A style remembered while 杂志 was the default hid the new 片场 default; key is now `lacuna.ximalaya.style.v2` | `web/e2e/ximalaya.spec.ts` |
| Episode open (V5) | A read error while re-picking old room tone made the episode impossible to open; now logged, retried next open | `tests/app/test_sweep2.py` |
| 记住 (V6) | Failure notice read 「这次没能改写（LACUNA 这次没有给出结果）」 | same |
| E2E | Windows: first page of a cold server took > 5 s (`learning.spec.ts:8`, #111), and the first 喜马拉雅版 visit draws its images (probably resvg loading the system fonts) past 5 s (`ximalaya.spec.ts:30`, main run of ceeea9c); those checks wait 20 s | — |

Note for the harness: Playwright `setInputFiles` with a non-ASCII *path* never reaches the page on a
POSIX-locale Linux box; specs pass such files as buffers (`sweep2.spec.ts`).

## Checked and fine
Library scopes with series rules (a series intro owned by one episode still applies elsewhere and survives
that episode's permanent delete), music chat only adds this episode's or shared assets, scope check on
changing a placement's file; speed re-applied when a new mix loads and on 试听这一处; V7 repair is read
through the same `SourcePool` by room tone, review, mix and export, while levels measure the recording as is;
the repair cache lives in the episode folder (goes with a permanent delete, never learning data); first
open of an older episode scans once (index cache means the 剧集 list doesn't trigger it).
