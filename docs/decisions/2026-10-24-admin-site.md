# The admin site: admin.lacunastudio.app

Date: 2026-10-24. Decided by Leon (admin thread; feature list, style, security and prototype in the project files
`lacuna/docs/admin/{features,style,security,proto}.html`, prototype https://claude.ai/artifact/KQG3abg9A1B2mMfC6x5aei).
Leon: 「OK，做吧，没问题。都按你的推荐，除了要一起做之外。」 Security: 「全部按着你的推荐走」 (typed).

## Decision
- One batch: the whole admin (93 of 109 features; the other 16 are 以后).
- Its own address, admin.<domain>, served by the real container but split off before anything else
  (`lacuna_app/admin_host.py`): the main address answers `/api/admin/*` with 404, the admin address answers no
  main-site API.
- Style B 石墨控制台: Geist, indigo accent (#4f46e5, dark #7c78ff), light by default, left sidebar; home shows
  待处理 first; feedback is a two-pane inbox; a person opens in a right-side drawer; charts are a big number and a
  small trend. Demo data is a top-bar switch that turns amber and saves nothing (actions only show a toast).
  Phone: feedback and requests. Interface in zh + en.
- Security (all 8 recommendations):
  1. Its own Cloudflare Access application, always on, never opened by the site door (deploy/provision.py).
  2. Only Leon's email is let in by Access; the app also checks the Access token's audience and that the person
     Access let in is the one signing in.
  3. Sign-in is password + authenticator code in one step; sessions last 8 hours (`__Host-` cookie, SameSite strict).
  4. Dangerous actions ask for the code again (good for 15 minutes); owner-only actions; typed confirmations
     (彻底删除 = the email, 立即清除 = the name, 关掉批准).
  5. Every admin sign-in emails an alert.
  6. The staff cards move out of the main site (after Leon's acceptance, see below).
  7. The admin never shows audio or transcripts.
  8. Passkeys are added before launch.
  Plus: every change needs the `X-Lacuna-Admin` header and the same origin; strict CSP and security headers; every
  change is in the 操作日志, which cannot be deleted.
- The 10 product decisions: indigo accent; demo actions only toast; beta seats counted by show, 20 in all; daily
  digest at 8:00 Vancouver time; a person is silent after 14 days; NPS (0–10) after the 3rd export, then every 3
  months; AI budget $300/month with emails at 80% and 100%, never stopping the service (the hard limit is set in the
  AI provider's console); raw events kept 13 months; everything in one batch; main-site staff cards removed after
  Leon's acceptance.
- Main-site pieces driven by the admin: the 站内公告 bar, 维护模式 (pauses new uploads and imports only),
  「想要更多时长」 in 设置 → 套餐与用量 (the owner approves each; never automatic), the NPS question.
- Request emails (试用申请, 搭档申请) link to the admin's 邀请与申请.

## Not now
- Passkeys (before launch). Removing the main-site staff cards (after acceptance). The 16 以后 features.
