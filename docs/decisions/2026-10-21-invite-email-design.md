# Invite email: design A 「夜航信笺」, HTML with a plain-text fallback

- Date: 2026-10-21
- Status: CONFIRMED（Leon picked A）
- Supersedes / changes: invite-mail-language (adds the HTML)

`lacuna_app/invite_mail.py` renders a dark letter card (logo inline as cid:lacuna-logo PNG, inviter, project,
role, one button, the link written out, expiry), zh or en like before. Subject 「Leon 邀请你使用 LACUNA」. If the
HTML send fails the plain-text mail is sent instead.

## Gmail dark mode (2026-10-21)
Gmail on iPhone flips light text dark in dark mode, so the white title and wordmark vanished on the navy band
(Leon's test). The white header and button text now sit in two black blend layers (screen + difference,
`invite_mail.white()`), which undo Gmail's change; the CSS matches only Gmail (`u + .body`), so other apps and
light mode look as before.
