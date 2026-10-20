# Sign-in (登录 / 注册 / 忘记密码)

Thread「登录与 Resend 邮件」, then「账号与权限」. Decisions: `docs/decisions/2026-10-17-local-sign-in.md`,
`2026-10-19-invites-roles-2fa.md`.

## State (2026-10-17)
- Built: `lacuna_app/auth.py`, `keystore.py`, `routes/auth.py` (API + 401 gate); web `features/auth/`
  (AuthGate in `main.tsx`, AuthScreen design B, AccountCard in 设置); a 401 from any call shows sign-in again.
- Tests: `tests/app/test_auth.py` (13), `web/e2e/auth.spec.ts` (5, default server with a fake mailer;
  the other E2E servers set `auth_skip_setup`).
- Slogan on the brand panel: "Mind the gaps. Keep the voice." (Leon's pick; English in both interface
  languages, generic for any editing work, not tied to the show). Logo: the V3「光晕」 mark (`features/brand/logo.svg`, PR #70).
- 2026-10-18 (PR #92, 首检 #2): signing in or creating the account always lands on 剧集 (`#/`), not on 设置 where
  the sign-out happened (`AuthGate`; covered in `auth.spec.ts`). Waiting for the 2026-10-18 batch validation.

## 2026-10-19: invites, roles, two-step sign-in (thread「账号与权限」, PR A)
- Built: invite-only sign-up, roles owner/admin/member, TOTP two-step (`lacuna_app/totp.py`) + recovery codes,
  15-minute lockout, signed-in devices, change password; 设置 cards 账号与安全 / 成员与邀请 (admins) / 邮件 (owner).
  `LACUNA_CLOUD=1` makes two-step mandatory, cookies Secure, first account needs `auth/setup-code.txt`
  unless Access proved it is `LACUNA_OWNER_EMAIL` registering that email.
- Owner-only API: `/api/app/api-key`, `/api/app/update/prepare|apply`, `/api/auth/config|resend-key|test-mail`.
- Tests: `tests/app/test_auth.py`, `test_auth_invites_2fa.py`; `web/e2e/auth.spec.ts` (6, incl. a cloud first run).
- PR B: workspaces (`lacuna_app/spaces.py`, `routes/spaces.py`, web `features/spaces/`): content belongs to a
  workspace; top-bar menu to switch; 设置 → 工作区; invites pick a workspace (default: a new one of their own).
  Decision `2026-10-19-workspaces.md`. Tests `tests/app/test_spaces.py`, `web/e2e/spaces.spec.ts`.

## Update notes
No extra install steps. Leon's existing account becomes 所有者 and signs in as before; two-step is optional on the
desktop (设置 → 账号与安全). The 设置 card 账号与邮件 is now split into 账号与安全 / 成员与邀请 / 邮件.

## Validated
- 2026-10-17 20:23Z: Leon validated sign-in on his PC (「没问题，验收通过」).

## 2026-10-20: email from lacunastudio.app (thread「邀请邮件发件域名」)
- Decision `docs/decisions/2026-10-20-mail-domain.md`. Provision mode `mail-domain` verifies the domain in Resend
  and writes its DNS records to Cloudflare; default sender `LACUNA <noreply@lacunastudio.app>`, old `@resend.dev`
  senders move to it. Tests: `tests/test_provision.py` (mail_domain), `tests/app/test_auth_invites_2fa.py`.
- Invite email language (decision `2026-10-20-invite-mail-language.md`): 「中文邮件 / English email」 select in both
  invite forms (`features/auth/MailLang.tsx`); the sign-up page of a fresh browser opens in the email's language.
  Tests: `test_invite_email_language_is_the_inviters_pick`, `test_spaces.py`, `web/e2e/auth.spec.ts`.
- Invite link fix (2026-10-20, Leon's staging E2E): links are `/invite/<token>` (path), not `#/invite/<token>` —
  Cloudflare Access's email sign-in drops a URL's #fragment, so a new invitee landed on the plain login page.
  Old `#/` links still open. A link opened where someone is signed in now says so (「退出并接受邀请」 /
  「继续用 …」) instead of dropping it. Tests: `web/e2e/auth.spec.ts`, `tests/app/test_auth_invites_2fa.py`.
