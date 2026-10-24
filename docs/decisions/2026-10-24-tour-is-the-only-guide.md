# The first-login tour is the only guide; 节目设置 on the show's 首页

Date: 2026-10-24. Asked for by Leon in the project chat ("开个线程把这些清掉", plus three show-navigation changes).

- The bubble tour on first login is the whole onboarding. After it, users are on their own; they can replay
  it from 设置 → 通用 (示例节目). Removed from the show's 首页: the 「入门 x/6」 checklist card, the top-bar
  「入门 x/6」 tag and the 「让 LACUNA 更懂这个节目」 节目资料卡 (with the import form's hint that pointed to it).
  Leon: the home looked messy and duplicated the tour.
- Nothing is lost: 一句话介绍, 专有名词 and 片头片尾 stay in 节目设置.
- Server: `/api/onboarding` keeps only `welcomed`, `tour`, `collab`, `sample`; `POST /api/onboarding/mark` and
  the `hidden` flag are gone. Old records' `done` list is ignored (dropped on the next sample reset/delete).
- 节目设置 has a button beside the show's name on its 首页 (the top-left menu alone was too hidden).
- 「所有节目」 is in the show menu even with only one show.
- An archived show's 节目设置 offers 永久删除 right there (its creator; same typed-name dialog as 所有节目).
  Deleting the only show is still refused (create another first).
