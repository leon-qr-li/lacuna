# Invite email language: the inviter picks it

Date: 2026-10-20 (thread「邀请邮件发件域名」; Leon: "什么决定是发中文还是英文的邮件…如果没做，做")

## Context
Invite emails followed the inviter's interface language (the request's `lacuna_lang` cookie); nothing let the
inviter write to an English-speaking guest from a Chinese interface.

## Decision
- Both invite forms (设置 → 成员与邀请, 项目设置 → 邀请协作 for site admins) get a select 「中文邮件 / English email」,
  starting at the inviter's interface language. `lang` goes with `POST /api/auth/invites` and
  `POST /api/spaces/{id}/invite`; `Auth.invite(..., lang)` writes the email inside `i18n.speaking(lang)`.
- The invite remembers its `lang`; `/api/auth/invite` returns it and a browser that never picked a language opens
  the sign-up page in it (a browser with a saved choice keeps its own).
- The premium HTML invite email (design A「夜航信笺」) is separate and not built yet.
