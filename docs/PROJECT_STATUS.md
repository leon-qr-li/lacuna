# LACUNA Studio — Project Status

_Last updated: 2026-10-16 21:40Z_

## Current phase
P0 → P1。方向已确认（D23 API 额度路径、D24 MVP 收窄）。

## Done
- Handoff 原件：`/mnt/project-files/lacuna/handoff/podcast_studio_handoff/`（10 份，全文已读）。
- 评估：`docs/00_TECH_LEAD_ASSESSMENT.md`；决策：`docs/DECISIONS.md`（D23–D28）；硬件约束：`docs/HARDWARE_PROFILE.md`。
- Leon 已把 Console org 链接到 Max 订阅（API 额度可用）。
- 新事实 D26：历史 raw 录音已删除，无 raw/final 配对 → S4 取消，学习改以 Studio 内实时反馈为主（D27）。

## In progress / waiting
1. Leon 的素材在其本机文件夹 `Projects`，正在请求设备文件夹访问（connect_device 卡片）以整理。
2. ✅ GitHub 仓库 https://github.com/leon-qr-li/lacuna 已就绪，docs 与 Handoff 已迁入 main（2026-10-16）。仓库是今后的权威来源；`/mnt/project-files/lacuna/` 为镜像 / 素材区。
3. 搭档 Mac 型号未知（不急）。

## Next action
- 拿到文件夹访问后：盘点素材，整理成 workspace 结构（raw/ assets/ inbox/ …），在 `.notes/inputs.md` 记录。
- 仓库就绪后：迁入 docs，建骨架 + CI 矩阵（ubuntu/windows/macos）。
- 并行：S2 ASR 对比（需真实片段）、S3 双轨 EDL/渲染（先用合成素材）、P2 低保真线框。
