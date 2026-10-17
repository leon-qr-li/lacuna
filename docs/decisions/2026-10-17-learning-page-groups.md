# 学到的规则: tabs by decision state, 10 per page, client-side

Leon (2026-10-17): rules keep piling up; by default show only what still needs his decision, hide decided ones but let him open them, page when there are many. Details left to Claude.

- Three tabs (segmented control, same look as the episode sub-tabs): 待你决定 (default) / 已生效 / 已不采用, with counts. Tabs rather than show/hide checkboxes: one question at a time, and the default view is exactly his to-do list.
- An adopted rule with new evidence sits in 待你决定 (it needs a decision) and also in 已生效 (its old version is still in force).
- 10 per page, numbered pager; the tab resets to page 1 and the page is clamped after a decision empties it.
- Client-side: `/api/learning` already returns all rules (hundreds at most); the slow part is re-reading episodes, which server paging would not fix. No API change.
- Chinese tab label 已不采用 (not 不采用) so the English can be "Rejected" while the button 不采用 stays "Reject".
