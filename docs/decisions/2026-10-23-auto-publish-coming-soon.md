# 自动发布: after beta; beta shows 「即将推出」

Date: 2026-10-23. Decided by Leon (thread 设计发布到各播客平台).

## Decision
- LACUNA is not a podcast host and never serves an RSS feed. Publishing, when it comes, only hands an episode to the
  show's existing host (through the host's API where one exists, else a guided manual upload).
- Direct publishing waits until after beta. It is not the selling point (the audio work is), and which hosts to
  support depends on who the beta users turn out to be.
- Beta shows only a short 「即将推出」 in 节目设置 → 发布, section 「自动发布」: one line, four checkboxes for the
  platforms LACUNA can surely reach through a host's RSS (Apple Podcasts, Spotify, YouTube, Amazon Music), and
  「想要的平台不在这里？告诉我们」. 喜马拉雅 and 小宇宙 are never offered there (no upload API; nothing to promise).
- What a show ticks is saved (`show.json` → `publish.auto_wish`) so the admin back office can count it later.
- The 「告诉我们」 link has no target yet; it gets one when the feedback page is designed (a separate batch).
- The old 「节目发布在哪儿」 picker is gone from the form. A show keeps its stored `publish.ximalaya`
  (Leon's 上传喜马拉雅 step stays); turning that step on for a new show is decided with the feedback/publishing work.

## Background
Research and the five open questions for after beta (which hosts first, guided pages, first-listing guide, show
settings, legal points): Claude Doc https://claude.ai/artifact/A7ZkbqmMzqohAdQr2ryYom. Approved mockup:
https://claude.ai/artifact/XDi1nMmjEy9rfmDTHEaEF1.
