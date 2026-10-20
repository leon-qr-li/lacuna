# Who adds new people; 剪辑力度 per editor with a per-host adjustment

- Date: 2026-10-20
- Status: CONFIRMED（Leon 18:24Z, typed: 「两个都选 A，都是你推荐的。」）
- Part of: `projects-albums` (steps 2 and 3)

1. **New accounts stay with LACUNA's owner/admins.** A project manager can invite people who already have a
   LACUNA account (they join at once); an email with no account is refused with 「现在只有 LACUNA 管理员能邀请新人注册」.
   Site admins can still send a sign-up invite that drops the person into the project. (Security: typed by Leon.)
2. **剪辑力度 is one level per editor** (设置 → 剪辑习惯: 轻剪 / 正常 / 狠剪), used in every project, including
   ones they were invited to. Each host in 项目设置 → 主持人 keeps only an adjustment: 比我平时更狠 / 一样 / 更松
   (one step up or down, kept in range). Migration: Leon's show → Leon 更狠, Pei 一样, everyone's level 正常,
   so his first cuts don't change. An old per-host `cut_level` reads as its step from 正常.
3. **Approved learned rules follow the editor too**: which rules are approved lives in the person's home
   (`<site root>/people/<hash>/learning/rules.json`); the evidence (decisions, asks, lessons) stays with each
   project's episodes. On the first request after the upgrade, each project's old `learning/rules.json` is
   copied once into each of its managers' homes (startup jobs such as stutter_rule_once run first).
   Without accounts (desktop / dev) everything stays in the workspace folder.

Known limit: a rule approved in one project shows as stale in another project until that project has
evidence for it; the AI uses only rules whose text the current project holds.
