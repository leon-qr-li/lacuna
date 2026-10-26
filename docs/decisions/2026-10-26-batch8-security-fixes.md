# Batch 8 security and product fixes (S1–S6, P2, P3) and the admin invite mail

- Date: 2026-10-26
- Status: CONFIRMED (Leon picked every option on the batch 8 decisions page, then typed 「都选完了，做」)

Found in the batch 8 regression's security probe; Leon chose the recommended option for each.

- S1 password-reset codes (`lacuna_app/auth.py`): at most 5 codes a day per email; after a code is guessed wrong
  5 times no new code for an hour; at most 20 code requests an hour from one address (counted for unknown emails
  too, so the limit says nothing about which emails have accounts).
- S2 `GET /api/app` from a browser on the shared server answers no busy list and no server folder; only the host's
  updater (loopback) gets them.
- S3 ending someone's sessions in the admin follows the same rank rule as every other account change.
- S4 the main site sends nosniff, X-Frame-Options DENY with `frame-ancestors 'none'`, and a Referrer-Policy. No full
  CSP (option B) for now.
- S5 a feedback screenshot must decode as the PNG or JPEG it claims to be.
- S6 cloud mode has one test, `cloud.enabled()`: LACUNA_CLOUD = 1 / true / yes.
- S7 unchanged: a disabled account signing in is told 「邮箱或密码不对」 (nothing about which accounts exist).
- P1 unchanged: renaming a host affects later imports only; 节目设置 already says so.
- P2 只听 members see a 「只听成员」 tag by the show name and greyed-out review / chat / restore / export buttons.
- P3 a GitHub workflow checks `/api/health` every hour from outside; when the site stays down the run fails and
  GitHub mails the owner.

Also (Leon 2026-10-26): one site owner only (he asked about a second owner, then kept one). Making someone a site
admin mails them design C 「权限对照卡」: what admins can and can't do, the first steps into the admin, and links to
the admin and the main site.
