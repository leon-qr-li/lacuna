# Approved rules stay approved when they gain examples

Leon, 2026-10-18: an adopted (已生效) rule that is re-learned with new examples must not go back to
「待你决定」. Its wording changes only because the prompt quotes examples; it is the same rule.

- A rule keeps its id (kind + category + host); while approved, `Learning.overview` replaces the frozen
  snapshot with the re-learned version, so the new examples apply at once. No "updated" state any more.
- Only a rule with a new id (a brand-new rule) is a candidate that waits for Leon's 采用.
- Rejecting / deleting is unchanged: re-learning never revives a rejected or deleted rule.

Supersedes the "approved version stays in force until Leon re-approves" part of D39 / PR #75.
