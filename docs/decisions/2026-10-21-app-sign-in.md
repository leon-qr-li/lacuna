# The app's own sign-in becomes the door: Turnstile, new-device email, 申请试用; Access off only on Leon's typed word

Date: 2026-10-21. Decided by Leon (batch 3 decision pack, questions 9–10, option A each; 03:01Z).
Supersedes / changes: `cloud-deploy` (Cloudflare Access in front of the site), when the door is opened.

## Decision
- Sign-in protection: password + mandatory two-step code + lockout (as before), plus Cloudflare Turnstile
  on the sign-in and 申请试用 forms (lacuna_app/turnstile.py; on only when the server has both keys) and an
  email when an account signs in from a new browser/system (lacuna_app/notice_mail.py; not on the first
  device). With Access off, a cloud server with no account yet is still closed to everyone (setup code).
- 申请试用 on the sign-in page: email, show name, a note. Open endpoint, Turnstile-checked, 1 per email and
  5 per address a day; the site owner gets an email; the list is in 设置 → 成员与邀请 → 试用申请 with
  发邀请 (a sign-up link, a show of their own) or 忽略. The answer never says whether an account exists.
- Cloudflare Access stays in front until Leon TYPES 「关掉 Access」. Then: `deploy/site-door.txt` = `open`
  (PR), Provision `recreate`: the main site's Access policy becomes bypass-everyone, a Turnstile widget is
  made, and the server gets `LACUNA_ACCESS=off` + the Turnstile keys. Staging stays behind Access.
  Way back: `access` + `recreate`. A plain `apply` never changes the door (a bypass policy in front of a
  server that still expects Access would lock everyone out).

## Why
Public beta needs strangers to reach a sign-up path; Access's email allow-list can't do that. The app's
sign-in already has 2FA and lockout; Turnstile stops bots and the new-device email tells people at once.
