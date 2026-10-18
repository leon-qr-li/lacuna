# UI backlog from 首次检测 (docs: /mnt/project-files/lacuna/docs/UI_BACKLOG_首次检测.md)

State (2026-10-18): all 28 items merged on main. #1 validated earlier; #2–#28 wait for Leon's validation in
the 2026-10-18 batch (release 2026.10.18.2) (steps: /mnt/project-files/lacuna/docs/验收_2026-10-18/00_完整验收清单.md).

| # | Item | PR | Details |
|---|---|---|---|
| 1 | 「剧集」 link in the top bar | #79 | below |
| 2 | Sign-in lands on 剧集, not 设置 | #92 | phase-04-import.md, auth.md |
| 3 | Archive / restore / delete episodes (learning kept) | #92, #99 | phase-04-import.md |
| 4 | Import: drag & drop + 「选择文件」 like the media library | #92 | phase-04-import.md |
| 5 | Honest import time left; 「每段约 10 分钟录音」 | #92 | phase-04-import.md |
| 6 | Review player speed (1×–2×, key S) | #86 | review-edit.md |
| 7 | Hosts evened out at import; 「声音」 step + chat volume | #94 | levels.md |
| 8 | Erase one host's sound, fill with own room tone | #90 | review-edit.md |
| 9 | 「记住」 confirms LACUNA's reading before storing | #91 | phase-05-learning.md |
| 10 | Voice input fixes homophones / names from context | #88 | voice-input.md |
| 11 | Previews 5 s either side of an edit (was 10 s) | #86 | review-edit.md |
| 12 | New step 本集学到的规则 (replaces the after-export summary) | #91 | phase-05-learning.md |
| 13 | In-app confirm dialog instead of window.confirm | #97, #99 | dialog-brand.md |
| 14 | Two title lookups at once both land | #97 | dialog-brand.md |
| 15 | Music picker: file name first | #93 | music-page.md |
| 16 | Background reduction default 22 dB (was 20) | #93 | music-page.md |
| 17 | 「全音量时长（秒）」 label | #93 | music-page.md |
| 18 | −5 s / +5 s on the music player | #93 | music-page.md |
| 19 | Strip click and player stay in sync (one player) | #93 | music-page.md |
| 20 | Music levelled on the part that plays; automatic level shown | #94, #96 | levels.md |
| 21 | Automatic / looping beds | #93 | music-page.md |
| 22 | Change a placement's type in place | #93 | music-page.md |
| 23 | Posters 2×2 | #85 | phase-10-cover.md |
| 24 | One framed 一句话改 bar (PromptBar) | #85 | phase-10-cover.md |
| 25 | 下载封面 also saves next to the audio | #85 | phase-10-cover.md |
| 26 | Show notes without tables + 「喜马拉雅版」 tab | #89 | show-notes-ximalaya.md |
| 27 | 喜马拉雅版 layout POC (merged into #26) | #89 | show-notes-ximalaya.md |
| 28 | Interface never names the AI vendor (AI = LACUNA) | #87 | dialog-brand.md |

## #1 「剧集」 in the top bar — done
- `web/src/features/episodes/`: nav link to the episode overview (`#/`) on every screen, first in the
  bar; `aria-current="page"` + navy tint while the overview is open. English label "Episodes" (shell en.ts).
- Test: `web/e2e/episodes_nav.spec.ts`.
