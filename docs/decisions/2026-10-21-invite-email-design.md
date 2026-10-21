# Invite email: design A 「夜航信笺」, HTML with a plain-text fallback

- Date: 2026-10-21
- Status: CONFIRMED（Leon picked A）
- Supersedes / changes: invite-mail-language (adds the HTML)

`lacuna_app/invite_mail.py` renders a dark letter card (logo inline as cid:lacuna-logo PNG, inviter, project,
role, one button, the link written out, expiry), zh or en like before. Subject 「Leon 邀请你使用 LACUNA」. If the
HTML send fails the plain-text mail is sent instead.

## Gmail dark mode (2026-10-21)
Gmail on iPhone recolours text in dark mode, so the white title and wordmark turned dark on the navy band
(Leon's test). A first fix (CSS blend layers, #163) did not hold in his Gmail. Now the dark band (logo, wordmark,
sunset rule, kicker, title) and the 接受邀请 pill are inline PNG pictures (`invite_mail.header_png()` /
`button_png()`, drawn with resvg, Inter + Noto Sans CJK from the image's fonts-noto-cjk), which no mail app
recolours. The alt texts carry the title and the button label; without a CJK font the HTML versions stand in.
