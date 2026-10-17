# Decisions (from 2026-10-17)

One decision per file: `<YYYY-MM-DD>-<slug>.md`, slug = a few English words in kebab-case (unique; check `ls`).
No running numbers: parallel threads kept taking the same next D-number. Cite a decision by its slug,
e.g. "decision `one-file-per-feature`". D01–D51 stay where they are (`handoff/07_DECISION_LOG.md`, `docs/DECISIONS.md`).

Template:

```markdown
# <one-line decision>

- Date: 2026-10-17
- Status: <Claude 技术决策 | CONFIRMED（Leon） | …>
- Supersedes / changes: <D45, or a slug, or —>

<what was decided and why, a short paragraph; details and numbers welcome>
```

A later decision that changes this one gets its own file and says so under "Supersedes / changes";
edit the old file only to add a line "Changed by: <slug>".
