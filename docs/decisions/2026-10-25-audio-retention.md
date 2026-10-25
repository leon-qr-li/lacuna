# Raw tracks kept 12 months after last use (reminder 30 days before, off during the beta); only the latest export is kept

- Date: 2026-10-25
- Status: CONFIRMED（Leon 2026-10-25「全部同意，都按着你的推荐」，第五批问题 2 B、问题 3）
- Supersedes / changes: —

`lacuna_app/retention.py`, run with the daily storage upkeep (`lacuna_app/routes/cold.py`). Raw tracks of an
episode not used (opened, edited, exported) for 12 months are deleted; 30 days before, the show's creator gets a
mail in their language listing the episodes, and any use resets the clock. Exports, transcripts, edit history and
show notes are kept forever. The rule is a switch (后台 → 系统健康 → 存储与保留), off during the beta, so nothing
is deleted then. Exports: once an episode has a newer export, the older export's audio files are deleted 7 days
later (the export record stays; it can be made again from the same cut); this switch is on. What happens to
accounts that don't pay after the beta is decided with the business model.
