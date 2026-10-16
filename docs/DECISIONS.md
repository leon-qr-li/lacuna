# LACUNA Decision Log (append-only)

延续 Handoff `07_DECISION_LOG.md` 的 D01–D22（全部继承，原文见 `handoff/`）。新决策从 D23 开始。

| ID | 日期 | 决策 | 状态 | 说明 / 取代关系 |
|---|---|---|---|---|
| D23 | 2026-10-16 | AI 运行时使用 Max 5x 自带的每月 $100 API 额度（Console org + API key，不绑卡、不开 auto-reload），直接调 Messages API；订阅 OAuth 不用于产品运行时 | CONFIRMED（Leon 已链接 org） | **细化 D01**：模型偏好与“无额外付费”保留，集成方式由“Claude Code 订阅”改为“Claude API + Max 赠送额度”。依据见 `00_TECH_LEAD_ASSESSMENT.md` §3 |
| D24 | 2026-10-16 | MVP 收窄：人声剪辑 + 审阅闭环 + 导出 + 系列片头规则 + 用户指定配乐的放置与 ducking。AI 主动推荐配乐片段、推断偏好规则、喜马拉雅自动化放到 MVP 之后 | CONFIRMED | 不改变 V1 总体愿景，只改顺序 |
| D25 | 2026-10-16 | 硬件约束：Leon Windows（Ryzen 5 3600 / GTX 1660 SUPER 6GB / 16GB RAM / 500GB SSD），采用 hardware-aware 分档 | CONFIRMED 约束 | 详见 `HARDWARE_PROFILE.md` |
| D26 | 2026-10-16 | **历史原始录音已不存在**，没有 raw/final 配对可供学习或评测 | CONFIRMED 事实 | **取代** Handoff 中“约 10 集 raw + final 可用”的假设（PRD Style learning、Journey 5、Roadmap 1C/P5、Feasibility Gate 1）。S4 取消 |
| D27 | 2026-10-16 | 学习模块升级为核心能力：以 Studio 内的实时反馈（恢复、覆盖、聊天修改、批准）为主要学习来源；Studio 自动保存每集 raw + 每个版本 + 最终成品，从此历史不再丢失 | PROPOSED by Claude，随 D26 生效 | 第一刀质量评测改为：新集上 AI 第一刀由 Leon 盲听打分 + 修改量统计 |
| D28 | 2026-10-16 | 不做通用 speaker diarization：Riverside 分轨即说话人；只做每轨 VAD + 串音检测 | Claude 技术决策 | 节省显存与时间 |
