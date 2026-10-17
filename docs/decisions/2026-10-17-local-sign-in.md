# Local sign-in with email codes through Resend

**Date:** 2026-10-17 · **Asked by:** Leon ("为了规范", a simple login: no third-party / SSO, use his free Resend account)

## Decision
- Accounts live on the machine: `<workspace>/auth/users.json` (scrypt, random salt) and `sessions.json`
  (SHA-256 of random tokens). Password check is local, so **sign-in works offline**.
- Session cookie `lacuna_session`: HttpOnly, SameSite=Strict. "30 天内记住我" (default on) = 30 days, else 12 hours.
- Once the first account exists, every `/api` call needs a session (401 otherwise). Open: `GET /api/health`
  and `GET /api/app` (the launcher's health/version checks), and the sign-in endpoints.
- The first account (owner) needs no email code. Later accounts need 设置 →「允许新注册」(off by default)
  plus a 6-digit email code. Codes: 10 min, 5 tries, 60 s between sends, kept in memory only.
- Email goes through the Resend HTTP API with `urllib` (no new dependency). The key is stored like the
  Claude key (`lacuna_app/keystore.py`: Windows user env `RESEND_API_KEY`, macOS Keychain, else a 0600 file),
  entered in 设置 → 账号与邮件, never shown. Sender defaults to `LACUNA <onboarding@resend.dev>`.
- Design B (brand panel + form) picked by Leon from three mockups (`screenshots/auth/`).

## Why / threat model
The server binds to 127.0.0.1, so sign-in does not protect files from someone at the computer (they can read
the workspace directly). What it does add: whoever opens the app must know the password, and other websites
open in the browser can no longer drive the local API (no SameSite=Strict cookie on cross-site requests).
It is also the base for Pei / multi-user later.

## Limits to know
- Resend free tier without a verified domain only delivers to the Resend account's own email (403 otherwise);
  free quota 100/day. Fine for Leon alone; Pei's account needs a verified domain + sender change.
- Locked out and no email: delete `<workspace>/auth/users.json`; the app asks for a new first account.
