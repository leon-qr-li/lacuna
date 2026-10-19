# Invite-only accounts, roles and two-step sign-in

**Date:** 2026-10-19 · **Asked by:** Leon (cloud move: "没有权限的人不可能 hack 进去… 除非是我邀请的", 2FA; future direction 1)

## Decision
- **No open sign-up.** The first account is the owner. Everyone else joins through an invite link that the
  owner or an admin creates in 设置 → 成员与邀请: bound to one email, 7 days, works once, only its SHA-256
  stored, the newest link for an email replaces older ones. The link is emailed through Resend and always
  shown for copying (Resend's free tier can't mail other people without a verified domain). 「允许新注册」 and
  the register email code are gone.
- **Roles (whole installation):** 所有者 owner (one; everything, incl. AI key, app updates, email settings,
  making admins), 管理员 admin (invites and manages members), 成员 member (uses the app). Nobody manages
  themselves or someone of equal or higher rank. Accounts can be suspended, deleted (their work stays) or have
  their two-step reset (lost phone). Existing accounts: the old `owner` flag becomes the owner, others members.
- **Two-step sign-in:** TOTP from any authenticator app (RFC 6238, our own 30-line implementation, no
  dependency), QR code drawn in the browser (`qrcode-generator`), plus 10 one-time recovery codes (hashed).
  A code can't be used twice. **Required for everyone in the cloud** (`LACUNA_CLOUD=1`): the first sign-in
  sets it up before any session exists. **Optional on the desktop app** (设置 → 账号与安全), so Leon's PC keeps
  working unchanged until the cloud is live. Password reset by email also needs the second step.
- **Lockout:** 5 wrong passwords or codes in 15 minutes lock the account for 15 minutes; in the cloud 30
  failures from one address (Cloudflare's `CF-Connecting-IP`) lock that address.
- **Devices:** every session records its browser and last use; 设置 lists them and can sign out one or all
  others. Changing the password signs out the other devices.
- **Cloud extras:** session cookie also `Secure`; the very first account needs the setup code the server writes
  to `<root>/auth/setup-code.txt` (and its log) on a fresh start, so whoever reaches a new server first can't
  become owner. Exception: when Cloudflare Access proved the request comes from `LACUNA_OWNER_EMAIL` and that is
  the email being registered, no code is asked (the server has no shell to read it from); two-step sign-in is
  still set up before the account can be used. Cloudflare Access in front stays the first gate (cloud analysis 2026-10-19).

## Not in this step
Content ownership (who sees which episodes, library and learned rules) comes next as per-workspace spaces;
passkeys and new-device login emails are possible later additions.
