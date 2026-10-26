# Batch 9: second full scan (code freeze)

Thread 「第九批：全局再扫一遍」 (Leon 2026-10-26: 「你再扫一遍，全局再扫」). Same method as batch 8
(`docs/status/batch-8.md`), with extra weight on #221 and #222.

## Runs (2026-10-26)
- pytest 881 passed / 17 skipped (real-model ASR and EP001 audio skip here); `npm run build` (types, i18n, brand) passes;
  E2E 153 / 153 passed.
- Code review of #221 / #222 (reset-code limits, `/api/app`, admin sessions, headers, screenshot check, admin invite mail,
  Provision) and of the per-show role checks and admin endpoints.
- Visual sweep on local servers (AI workspace without accounts; admin demo data; sign-in pages): zh / en × dark / light ×
  1440 / 1024 / 390, 504 screenshots plus an automatic check for sideways scroll, clipped text and text off screen; the
  admin invite mail rendered in zh / en at 700 and 390.

## Fix PR 1 (no security changes)
- Archived shows: review, chat, nearby / timeline restore and export are greyed out like a 只听 member's (they clicked into
  the server's 「已归档」 refusal); the chat box says 「这个节目已归档，只能查看。恢复后才能修改。」.
- Admin, phone: the user drawer was pushed wider than the screen in English (the 「在哪些设备登录着」 table); the drawer's
  column can't grow past the phone and the two date columns are one cell on two lines.
- Admin, 1024: tables whose rows end in buttons (邀请与申请, 节目与剧集, 卡住的剧集, 回收区) put the buttons out of sight to
  the right; they turn into cards up to 1100px (`.a-t-cards.md`). 用户 and 操作日志 keep the table (data pages, they scroll).
- Admin invite mail on a phone: both buttons the same width.
- E2E hygiene: `/api/auth/_test/reset` also clears the new reset-code counters.

## Waiting on Leon (security, his typed words): decisions page
Found by the review; fixes are written and tested, held until he types OK:
1. A non-owner admin could bring back an admin the owner deleted (both recycle bins): owner only.
2. 「退出对方所有登录」 and 「重置两步验证」 left the person's admin-site sign-ins open: they end too.
3. The screenshot check (S5) decoded any picture: a 0.5 MB PNG claiming 12000×12000 used ~630 MB; refused above 40 M
   pixels before decoding (also show pictures).
4. Reset-code limits (S1) could be passed by parallel requests (checks and counting now under the lock, before the mail).
5. The 「今天发够了」 / 「错太多次」 answers only appeared for real accounts (told which emails exist): every email is
   counted alike. Someone who knows an email can still use up its 5 codes a day (inherent to a per-email limit).

## Left as noted
Review titles stay in the first cut's language; 用户 / 操作日志 tables scroll sideways at 1024; data pages on a phone
(系统健康) scroll; manual transcript cuts, undo, music and show notes for 只听 / archived still answer the server's refusal
(outside P2's list).

## Next action
Merge PR 1 → deploy. Security PR after Leon's typed OK.
