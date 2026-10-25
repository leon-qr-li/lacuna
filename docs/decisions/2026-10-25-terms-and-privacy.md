# Terms of Service + Privacy Policy draft in the site; agreeing is required in the cloud and recorded per account

- Date: 2026-10-25
- Status: Claude 技术决策 (batch 6, Leon's 「做」 on the coordinator's proposal 2026-10-25 04:19Z); the text is a
  DRAFT for the lawyer, placeholders below to fill before public launch
- Supersedes / changes: —

The documents are Markdown in `web/src/features/legal/docs/` (`terms|privacy` × `zh|en`), shown at `/legal/terms` and
`/legal/privacy` by `AuthGate` before any sign-in (so an invitee can read them; Cloudflare Access still guards the
whole site until it is turned off before the beta invites). The sign-in screen links both; 申请试用 says "submitting
means you have read the privacy policy"; 设置 → 账号 shows the links and the version agreed to.

- Creating an account (first account or from an invite) has the box 「我已阅读并同意 用户条款 和 隐私政策」. The server
  stores `users[email].terms = {v, at}`. In the cloud the server refuses a sign-up without the current version
  (`lacuna_app/legal.py VERSION`); on a development checkout it is optional so tests and local runs don't need it.
- Accounts that agreed to an older version, or to none (everyone made before 2026-10-25: Leon, Pei, test
  accounts), see 「请确认用户条款和隐私政策」 after signing in (cloud only) and agree once (`POST /api/auth/agree`).
- Bump `VERSION` for any change people must agree to again (the lawyer's version, the company entity). A typo fix
  doesn't need it. `tests/app/test_legal.py` checks every document names it.
- Content choices (overseas standard): audio stored in the US (DigitalOcean SFO3, R2 WNAM), never sent to any AI;
  only text + numbers go to "an AI model provider in the US" whose contract forbids training. Providers are named by
  category, not by name, because of decision `ai-called-lacuna` (users never see the AI vendor); GDPR Art. 13 allows
  "categories of recipients", and the policy offers the named list on request. The lawyer should confirm.
- Retention stated as built: raw tracks 12 months after last use (paused in beta), older exports 7 days, deleted
  shows/accounts erased within 60 days (decision `deleted-kept-60-days`: users now learn the 60 days from the policy,
  which privacy law requires), restic backups 30 daily + 12 monthly, usage events 13 months.
- DMCA: notice / counter-notice / repeat-infringer policy written; the designated agent isn't registered yet.
  「请只上传你有权使用的音乐」 is in the terms (§5) and in the consent screen.
- Age 18+, liability cap = fees paid in 12 months or USD 100, no charge without explicit agreement.

Placeholders (`【待定：…】` / `[TBD: …]`, highlighted on the page) to fill before public launch: operating entity
and its address (Canada vs US not decided), governing law and court, DMCA designated agent (US Copyright Office,
$6), contact / privacy email (no inbox exists yet; 「反馈」 in the app is the channel meanwhile), cross-border
safeguard for EEA/UK (SCCs), EU/UK representative if required, which language prevails.
