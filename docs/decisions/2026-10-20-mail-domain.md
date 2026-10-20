# Invite and sign-in email from lacunastudio.app

Date: 2026-10-20 (thread「邀请邮件发件域名」; Leon: 「现在就做」)

## Context
Resend was still in test mode: mail from `onboarding@resend.dev` only reaches the Resend sign-up address, so an
invite to any other email failed with the "测试模式" error.

## Decision
- Verify `lacunastudio.app` in Resend. `python deploy/provision.py mail-domain` (Provision workflow, mode
  `mail-domain`; `mail-plan` only shows) adds the domain with the `RESEND_API_KEY` secret, writes Resend's
  sending records into the Cloudflare zone (DKIM `resend._domainkey`, SPF TXT + MX on `send.`, all DNS-only) plus
  a reporting-only DMARC (`_dmarc`, `p=none`) when none exists, then asks Resend to verify. It never touches the
  site's own records (tunnel CNAMEs, Access) or the bare domain's MX.
- Default sender `LACUNA <noreply@lacunastudio.app>` (`lacuna_app/auth.py` `DEFAULT_SENDER`), on the real site and
  staging. A saved sender still on `@resend.dev` moves to it on start; any other address chosen in 设置 → 邮件 stays.
- No mailbox receives at `noreply@`; replies are not expected.
