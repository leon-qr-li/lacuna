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
| D29 | 2026-10-16 | **更正 D26**：Leon 提供了一集完整的 raw 双轨 + 他手剪成品（EP001，73.5 min → 61.4 min），已验证成品由这两轨剪出。其余历史 raw 不存在 | CONFIRMED 事实 | 恢复 S4（单集对齐）并作为 S5 第一刀评测的地面真值；D27 学习策略不变 |
| D30 | 2026-10-16 | 逐字 ASR = Paraformer-large zh（sherpa-onnx int8，每轨 Silero VAD），所有硬件档位通用；SenseVoice-Small 作交叉校验；Whisper 仅可作 cuda-6gb 上的专有名词提示，绝不作转写源；所有剪辑点按信号能量谷精修 | CONFIRMED（S2 证据 + Leon 2026-10-16 抽查 raw 19:00–20:00 无漏字多字） | 见 `spikes/s2_asr/REPORT.md` |
| D31 | 2026-10-16 | 编辑模型与渲染器必须原生支持**每轨独立**时间编辑（单轨 slip、重叠串行化、单轨删短声），停顿收紧到约 0.4s 而非删除；每轨响度匹配为默认步骤 | Claude 技术决策（S4 证据） | 见 `spikes/s4_alignment/REPORT.md`；EP001 作为按轨评测的地面真值 |
| D32 | 2026-10-17 | 编辑规则 R002（对 Leon 狠、对 Pei 稍狠但更宽）与 R003（保留适量口癖，不能太干净）生效，记录于 `docs/EDITORIAL_RULES.md` | CONFIRMED（Leon 明确） | 产品规则可比 EP001 历史剪法略严于 Pei，因此 S5 评分中 Pei 的“误删”需结合试听判断 |
| D33 | 2026-10-17 | AI 第一刀导入规则：单轨 `cut` → 该轨 lift（对方保持连续）；若对方轨附近无字（且非单轨杂声）→ 双轨 ripple cut；`tighten_pause` 从停顿中间删多余部分；`slip` → 引擎 SlipRegion；`keep_flag` → 未应用的建议。需要 Leon 判断 = 内容删减 或 把握度 < 0.6 或 删掉说话 > 1.5 秒；排序：内容在前，其余按删除时长；其余为常规清理（按类别汇总、自动应用、可恢复） | Claude 技术决策 | 实现见 `lacuna_app/ai_cut.py`、`lacuna_app/review.py`；阈值待 Leon 审完一集后校准 |
