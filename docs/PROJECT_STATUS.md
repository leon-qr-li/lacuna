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
1. ✅ 素材已整理到 Leon 本机 `C:\Projects\LACUNA_Workspace\`（episodes/EP001_样本集/raw + reference，assets/，inbox/，exports/）。EP001 = 一集完整 raw 双轨 + 手剪成品（见 D29、`.notes/inputs.md`）。
2. ✅ GitHub 仓库 https://github.com/leon-qr-li/lacuna 已就绪，docs 与 Handoff 已迁入 main（2026-10-16）。仓库是今后的权威来源；`/mnt/project-files/lacuna/` 为镜像 / 素材区。
3. 搭档 Mac 型号未知（不急）。

## Spike results (2026-10-16)
- S2 ASR：`spikes/s2_asr/REPORT.md` → Paraformer 推荐（D30）。
- S4 对齐：`spikes/s4_alignment/REPORT.md` → 470 处剪辑、两轨大量独立编辑（D31）。

## Next action
- S4：EP001 raw→final 完整对齐图（保留/删除/移动/插入音乐），作为评测地面真值。
- 仓库就绪后：迁入 docs，建骨架 + CI 矩阵（ubuntu/windows/macos）。
- 并行：S2 ASR 对比（需真实片段）、S3 双轨 EDL/渲染（先用合成素材）、P2 低保真线框。
