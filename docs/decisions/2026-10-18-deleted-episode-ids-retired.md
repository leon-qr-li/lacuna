# A permanently deleted episode's id is never used again

- Date: 2026-10-18
- Status: Claude 技术决策（全面测试发现的 bug 修复）
- Supersedes / changes: —

Learning evidence is filed by episode id (`learning/decisions|lessons|asks|chats/<id>.json`) and is
never deleted (habits are only iterated). Before this, 永久删除 freed the id: the import form even
proposed it again, and a new episode under that id overwrote the old review snapshot on the next
「学到的规则」 visit and showed the old episode's 「本集学到的规则」 as its own. Now an id that still has
learning evidence but no episode is retired (`archive.retired_ids`): `next_id` skips it and an import
under it is refused with a message. Retired ids cost nothing (Leon's numbering simply moves on).
