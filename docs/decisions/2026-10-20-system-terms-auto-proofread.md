# System terms for every project, and old episodes are proofread by themselves

- Date: 2026-10-20
- Status: CONFIRMED（Leon, 2026-10-20 20:11Z: "加一个系统的专有名词 … 只有管理员能控制"; "这个应该是自动实现的"）
- Supersedes / changes: transcript-terms (the 「校对专有名词」 button is gone)

On top of each project's own terms there is one list for the whole installation (`<installation>/system_terms.json`,
`lacuna_app/system_terms.py`), shown on 设置 to everyone and changed only by the site owner / admins (site role,
auth.py; project roles don't count). It starts with ChatGPT and Claude Code (the recogniser wrote 拆GPT).
Every project's transcripts are proofread with it.

Nobody clicks to proofread: each episode remembers the glossary it was last proofread with (`term_check.json`,
a hash of the terms and corrections). When an episode opens whose hash differs (imported before this existed, or
project / system terms changed since), the page proofreads it right away and a notice lists what changed. New imports
are proofread during the import and count as checked. A failed request is not remembered, so it is asked again
next time. Cost stays ~$0.02–0.05 per hour of audio, once per change of the terms.
