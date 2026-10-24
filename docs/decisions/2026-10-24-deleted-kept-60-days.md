# Deleted shows and accounts are kept 60 days; every show can be deleted

Date: 2026-10-24. Leon: 「节目都应该一样」 and 「即使永久删除了…存60天之内，这是我们定的」, then 「做，现在做」 on the
condition that learned rules and 剪辑力度 don't change.

- 永久删除 of a show moves it to the 回收区 (`<root>/trash/<sid>-<time>/`: files, picture, its record). Restoring moves
  the files back to exactly where they were, so absolute paths inside episodes stay valid. A restored show comes
  back archived; a manager restores it from 节目设置.
- The first show ("main", files at the data root) is no longer special for deleting: only its own entries
  (`trash.SHOW_ENTRIES`) move; accounts, people's rules, other shows and models stay. A site meta flag keeps the
  start-up adoption from making it again. Nothing is moved on deploy: files only move when someone deletes.
- Deleting an account keeps its record and the shows it was in (site meta `trash_user:<email>`); restore brings
  both back and the old password works.
- Learned rules and 剪辑力度 live in `people/<hash>/` and are never touched by either delete.
- After 60 days a sweep (start-up, every 6 h, and on listing) removes them for good.
- The site owner and admins see the 回收区 in 设置 → 成员与邀请 (moves to the admin site when that is built).
- Sample shows are copies and still go at once.
- Open: privacy policy must state the 60-day retention; an "erase now" for GDPR requests (owner) when the admin
  site is built; beyond beta the 回收区 can move to R2 to save disk.
