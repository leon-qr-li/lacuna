# 用户动态: the admin sees what one account did lately

Date: 2026-10-31. Leon's ask (「我能不能看到一个人最近的操作…前提是不影响 performance」), design page
https://claude.ai/artifact/5vbdDaXTaenHN2DLsCCyVh, Leon 「都按推荐做」 (all seven recommendations).
Supersedes / changes: extends 2026-10-21-event-log (failed changes, details, write off the event loop).

## Decision
1. **Read only.** 用户动态 reads the `events` table the main site has written since 2026-10-21 (index `uid, ts`);
   it adds no write to anything a user does.
2. **Where:** the user drawer's 最近动态 (last session, last 7 days, latest five, 「查看全部动态」) and a full page
   `/activity?u=<email>` (days → sessions split at 30 minutes idle → merged repeats; filters 全部 / 剪辑 / AI /
   导入导出 / 账号与节目 / 只看失败; seven days at a time, 「加载更早的动态」). No site-wide feed yet.
3. **A little more is logged, in the same rows:** a change that failed (5xx, or 4xx other than 401/403/404) is
   `<event>.failed` with its status; `events.note()` puts numbers on the request's own row (seconds cut, fillers
   removed); exports log `export.done` / `export.error` from their thread. "Opened an episode" is not logged.
4. **The middleware writes in a worker thread** (`asyncio.to_thread`) after the response went out, so the event
   loop never waits on the disk. (The design page said "queue, flush every second"; a worker thread per row gives
   the same thing with no lost rows on a crash, so no queue was needed.)
5. **Looking is audited:** the first look at an account in 30 minutes (drawer or page) is `user.activity` in the
   操作日志.
6. **Privacy draft** (zh + en, no version bump: the text is a draft until the lawyer) says the site owner can view
   an account's usage records, without content, and that each look is recorded.
7. Per-show activity (按节目看谁做了什么): later.

## Why
The data already existed, so the page costs the user nothing; measured on a dev machine a row is ~1 ms to write
and a 100-row lookup in 500k rows ~0.13 ms. Moving the write off the event loop removes the one cost the log had.
If the site database moves to a server database later the `events` table moves as is; the page doesn't change.
