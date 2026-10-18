# Full scan: complete test pass (2026-10-18 night)

Thread「全面测试与修复」. Ran the whole pytest suite and every E2E on latest main, scanned the
interactions between the 26 首检 changes, fixed what was broken. Each fix has a test.

## Fixed (PR: full-scan fixes)
| Area | Bug | Test |
|---|---|---|
| 单轨抹除 (#8) | Room tone for an erase more than 30 s into a track came from the wrong place (offset relative to the search window), often the host's own speech | `tests/app/test_full_scan_audio.py` |
| 配乐调平 (#20) | A music part shorter than 0.4 s measured -inf and played at its raw file level (~14 dB too loud) | same |
| 配乐试听 | Changing the music while the old mix was streaming ended the stream short of its Content-Length (server error in the console) | `tests/app/test_stream_length.py` |
| 永久删除 (#3) | A deleted episode's id was proposed again; a new episode under it overwrote the old review snapshot and inherited its lessons | `tests/app/test_full_scan_episodes.py`, decision `deleted-episode-ids-retired` |
| 永久删除 (#3) | A request from another tab during deletion re-cached the episode, which then kept answering after its folder was gone | same |
| 记住 (#9) | Confirming 记住 again for a rule once deleted returned 404 (and still wrote half the ask) | same |
| 确认框 (#13) | Tab to 取消 + Enter confirmed; other keys (Ctrl+Z, review shortcuts) reached the page under the dialog | `web/e2e/dialog.spec.ts` |
| show notes (#26) | Table → list lines: an escaped `\|` split its cell; tables without outer pipes were left as tables | `tests/app/test_full_scan_publish.py`, `web/e2e/markdown.spec.ts` |
| 导入 | Words timed past the end of a shorter track gave NaN energy in the features sent to the AI | `tests/app/test_rehearsal_fixes.py` |
| E2E | ECONNRESET flake: uvicorn's 5 s keep-alive vs. a test reusing the connection; E2E servers now keep connections 120 s | — |

## Fixed (second PR; found by the 代码与性能优化 thread, handed over)
| Area | Bug | Test |
|---|---|---|
| 发布资料 / 海报 | An answer still on its way when the page was left started a polling chain that never stopped (and could show the previous episode after switching) | `web/e2e/publish_poll.spec.ts` |
| 登录 | Library upload, voice input and track upload used their own fetch: a 401 showed an inline error instead of the sign-in screen | `web/e2e/auth_expiry.spec.ts` |
| 素材库 | Without ffmpeg the soxr check crashed before the 「没有找到 ffmpeg」 message; a failed decode could leave a `.part.wav` | `tests/app/test_full_scan_library.py` |

## Checked and fine
Per-track gain applied exactly once in preview and export; music levels follow host gain; erase keeps
the timeline length in export; gain undo/redo survives reload; old episodes without levels.json; archive
keeps all learning evidence and restores exactly; 记住 stores nothing before confirm; no window.confirm /
alert / prompt left; 喜马拉雅版 HTML escaping; dictation fix falls back on timeout/error.

## Not changed (behaviour, not a bug)
An archived episode can still be opened by URL (hidden from the list only; tested on purpose).
Edit titles in the review list stay Chinese in English mode (written at import; older behaviour).
