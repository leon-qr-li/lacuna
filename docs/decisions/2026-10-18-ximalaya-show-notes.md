# 喜马拉雅版 show notes: no tables, three layouts, timestamps as text (backlog item 26)

**Context.** The 喜马拉雅 description editor has only 正文/标题, bold, font, image, tag, quote and
rule: no tables, no lists, a single newline is swallowed and pasted text can carry bold along.
Leon tested that images and timestamps in the description work, and that they sync well to 小宇宙.

**Decision.**
- Show notes never contain a table: the brief says so, the approved example lists films one per
  line (「- 《片名》英文名：导演/备注」), `render_markdown` writes lines, and `untable` turns any
  table (in Leon's edits or a pack saved before this change) into lines on save and on open.
  The web Markdown renderer also lays a table out as lines, so a copy never carries `<table>`.
- New episode sub-tab 「喜马拉雅版」 (`lacuna_app/ximalaya.py`, `routes/ximalaya.py`,
  `web/src/features/ximalaya/`): the current show notes Markdown (Leon's wording) in three layouts,
  杂志 (words, quotes, rules), 片场 (title cards / end credits, English labels, ▍ ◆), 图文 (title
  banner + films card images, rest text). Copy puts rich HTML (one `<p>` per line) and plain text
  (a blank line between lines) on the clipboard together.
- Hard rule: every timeline line starts with its timestamp as plain text, never bold, never in an
  image, so it is a jump link on 喜马拉雅 and 小宇宙. Only the films list may be an image, and its
  names stay as a text line too.
- Images are drawn locally from SVG with resvg (like the cover, D49), Chinese from the system font
  (微软雅黑 on Windows). The editor can't take an image from a paste, so the copied text carries a
  【插图】 line where Leon uploads the PNG with the editor's image button
  (`exports/<ep>/publish/ximalaya/`). If drawing fails, 图文 falls back to words only.

**Open.** Leon tests the three layouts in the real editor and picks; the unused ones can go later.
