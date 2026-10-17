# LACUNA App Roadmap (from POC to app)

_Started 2026-10-17, after Leon passed the POC (AI first cut + sample previews heard on his PC)._

How we work (Leon, 2026-10-17):
- Small phases. Each phase ships to Leon's PC; he validates it before anything that depends on it starts.
- Phases with no dependency between them may run in parallel threads, **at most 2–3 at once** (Leon validates them all). Check dependencies first; quality over speed.
- Every phase report says: what was done, which features were added, and how Leon validates it (what to open, which steps, what counts as pass).
- New ideas from Leon are added here at any time; order is re-checked when they land.
- This file is the plan only. Each phase's state, build notes and open issues live in its own `docs/status/phase-…md` (one file per phase, so parallel threads don't edit the same file). Edit the table here only to add or re-plan a phase.

Prerequisites beyond the POC: none block development. Only person-only item: `ANTHROPIC_API_KEY` on Leon's PC (D23), needed from phase 3 on. A second raw episode is needed for phase 4's real acceptance, not to build it.

| # | Phase | What Leon gets | Depends on | Parallel with | State and details |
|---|---|---|---|---|---|
| 1 | 审阅提速 | 剩下全部通过（一步可撤销）、决定后自动跳到下一条、Y/R 快捷键、过目进度、只看没过目的、AI 未删建议可以“不删，保持原话” | — | 母带与导出 (thread) | [status/phase-01-review.md](status/phase-01-review.md) |
| 2 | 导出成品 | 一个按钮导出整集 WAV / MP3（-16 LUFS / -1 dBTP），带进度，导出后能在文件夹里找到 | 母带与导出 thread merged (`lacuna_core`) | 3 | [status/phase-02-export.md](status/phase-02-export.md) |
| 3 | 真 AI 对话 | 聊天框接 Claude API：在任意位置说“这段删掉 / 停顿短一点”，AI 给出可试听的修改 | Leon's API key (set 2026-10-17) | 2 | [status/phase-03-chat.md](status/phase-03-chat.md) |
| 4 | 新一集导入 | 在 App 里选两条分轨 → 后台跑 ASR、分析、AI 第一刀，任务面板显示进度，完成后直接进入审阅 | 3 (first cut runs through the API at runtime) | 5 | [status/phase-04-import.md](status/phase-04-import.md) |
| 5 | 从审阅里学习 (D27) | Leon 的恢复/保留变成规则与阈值校准，下一集第一刀更像他 | Leon's full review of EP001; 3 | 4 | [status/phase-05-learning.md](status/phase-05-learning.md) |
| 6 | 片头、配乐与 ducking (= 6a) | 系列片头规则、指定配乐的放置与压低人声下的音乐、素材库 | 2 (mix bus + export) | 9 | [status/phase-06a-music.md](status/phase-06a-music.md) |
| 7 | 打包与更新 | 双击更新（不再靠远程装机）、Mac 实机跑通（Pei） | — (any time; best after 2) | any | [status/phase-07-packaging.md](status/phase-07-packaging.md) |
| 8 | UI 审美迭代 | 视觉与布局打磨 | flows stable (after 4) | 5–6 | not started (add `docs/status/phase-…md` when it starts) |
| 9 | 发布资料包 | 标题（可换候选）、一句话简介、show notes（D40 样式）、成品时间线上的章节、专有名词核对，一键复制（富文本 + Markdown） | 2 | 6a | [status/phase-09-publish.md](status/phase-09-publish.md) |
| 10 | 海报 | Claude 按本期内容写 3–4 版极简 SVG 海报，本地渲染 PNG，Leon 挑一版或一句话改 | 9 | 6a | [status/phase-10-cover.md](status/phase-10-cover.md) |
| 11 | 辅助发布 | 发布页（文件、文字、海报、清单、打开上传页）+ 发布/同步状态核实；之后再试浏览器代填 | 9, 10 | — | not started (add `docs/status/phase-…md` when it starts) |
| 6b | AI 推荐配乐 | AI 提议放音乐/台词的位置，从库里原声的真实分析中给 2–3 个候选片段 | 6, 5 | — | not started (add `docs/status/phase-…md` when it starts) |
