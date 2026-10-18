# Sign-in (登录 / 注册 / 忘记密码)

Thread「登录与 Resend 邮件」. Decision: `docs/decisions/2026-10-17-local-sign-in.md`.

## State (2026-10-17)
- Built: `lacuna_app/auth.py`, `keystore.py`, `routes/auth.py` (API + 401 gate); web `features/auth/`
  (AuthGate in `main.tsx`, AuthScreen design B, AccountCard in 设置); a 401 from any call shows sign-in again.
- Tests: `tests/app/test_auth.py` (13), `web/e2e/auth.spec.ts` (5, default server with a fake mailer;
  the other E2E servers set `auth_skip_setup`).
- Slogan on the brand panel: "Mind the gaps. Keep the voice." (Leon's pick; English in both interface
  languages, generic for any editing work, not tied to the show). Logo: the V3「光晕」 mark (`features/brand/logo.svg`, PR #70).
- 2026-10-18 (PR #92, 首检 #2): signing in or creating the account always lands on 剧集 (`#/`), not on 设置 where
  the sign-out happened (`AuthGate`; covered in `auth.spec.ts`). Waiting for the 2026-10-18 batch validation.

## Update notes
After updating, the app opens on「创建你的账号」(first account, no code). Then 设置 → 账号与邮件: paste the
Resend key (re_…), 发测试邮件. No extra install steps.

## Validated
- 2026-10-17 20:23Z: Leon validated sign-in on his PC (「没问题，验收通过」).
