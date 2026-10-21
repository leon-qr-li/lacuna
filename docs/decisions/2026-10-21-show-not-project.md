# The interface says 节目 / Show, not 项目 / Project

Date: 2026-10-21. Decided by Leon (thread 下一批, 01:48Z: 「项目这个词不如节目好」, then 「并进一起改」).

## Decision
Everything the user reads calls a project a **节目** (English **Show**): 我的节目 / My shows, 新建节目, 节目设置 /
Show settings, 整个节目, server errors and the invite email alike. The hierarchy reads 节目 → 专辑 → 剧集.
In 节目设置's side nav the first group, formerly 「节目」, is now 「基本」 / General so it doesn't repeat the page name.

## Why
Podcasters already call what they make a 节目; 项目 reads like office software.

## Scope
Interface text only (`t()` / `tr()` strings and their English). Code, identifiers, routes (`#/project`,
`/api/spaces`), test ids and stored data keep "project" / "space". Stored names users typed are untouched.
