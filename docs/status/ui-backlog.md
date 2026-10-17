# UI backlog from 首次检测 (docs: /mnt/project-files/lacuna/docs/UI_BACKLOG_首次检测.md)

## #1 「剧集」 in the top bar — done
- `web/src/features/episodes/`: nav link to the episode overview (`#/`) on every screen, first in the
  bar; `aria-current="page"` + navy tint while the overview is open. English label "Episodes" (shell en.ts).
- Test: `web/e2e/episodes_nav.spec.ts`.
