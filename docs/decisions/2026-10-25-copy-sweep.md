# Batch 7: one set of words, the walkthrough fixes, and a speed test

- Date: 2026-10-25
- Status: CONFIRMED（Leon picked every recommended option on the batch 7 decisions page,
  https://claude.ai/artifact/Q7kCPtogpamxffd7ZSoJTK, 2026-10-25 16:55Z）
- Supersedes / changes: `ai-called-lacuna` (extended to every place, not only the vendor name)

**Words (W1–W12).** The assistant is always 「LACUNA」 (panel, input, 「LACUNA 初剪」), never 「AI 制作人」.
Transcript = 逐字稿; the first pass = 初剪; checking edits = 审阅; the episode image = 封面; people see
「LACUNA 团队」, never 站长 / 站点管理员 (the admin area keeps them); roles 管理员 / 剪辑师 / 只听; people who
work on a show = 协作者 (collaborator); the product is LACUNA in the interface (LACUNA Studio only in the
legal pages and mail sign-offs); the editing-strength ends are 少剪 … 多剪; the learning page says
「AI 漏掉、你自己删的」 and 「你的取舍例子」; AI cost is never shown to users (admin only).
Desktop-era wording (本机, 文件夹, App) is gone; nothing promises publishing before it exists.

**Errors (B25).** A user never sees an API status, key or billing word. LACUNA's errors are one of two plain
sentences: 「LACUNA 现在有点忙，请稍后再试」 (timeouts, rate limits, overload) or 「LACUNA 暂时用不了…点「反馈」告诉我们」;
the cause goes to the server log (`editor.error_message`). A page that fails to load shows a box with the
reason, 重试 and a way back (`features/states`), never `Error: Internal Server Error`.

**Look (T1–T11).** 下一步 sits in the step bar's row (the slot is always there, so tabs never jump). Two page
widths: reading steps 880 px, workbench steps 1280 px (`--w-read`, `--w-work`) and one step-title style.
Episode tiles show the chosen cover else the show's colour, with a status stripe; the home buttons are one
primary plus one row of secondary. Empty pages: icon + one sentence + the next action. The current plan has a
brand-edge column and a 「当前」 tag. 两步验证已开启 is green. The sign-in theme button uses the app's sun/moon.
The admin uses the LACUNA mark and the 夜航 palette (layout unchanged). Phones: the top bar folds into a menu,
the LACUNA panel is a drawer, no page scrolls sideways. Under 1280 px the LACUNA panel starts closed and
pushes the page over. Members are managed only in 节目设置 → 协作者 (the top-bar 邀请协作 opens it).

**Speed test (S1).** An owner-only 「测速」 in admin → 系统健康 → 存储与保留 sends a 200 MB random file to the
R2 bucket and back, shows seconds and Mbps each way, then deletes the object and the local files
(`lacuna_app/speedtest.py`). Not on staging.

**How copy changes are checked (Leon 16:55Z).** Every screen whose words changed is screenshot in zh/en,
dark/light and at 1440 / 1024 / 390 px, and checked for overflow and looks before it ships.
