# LACUNA Studio — Tech Lead 接手评估 v1

- 日期：2026-10-16
- 作者：Claude（AI Technical Lead / Product Designer / Lead Engineer）
- 输入：`/mnt/project-files/lacuna/handoff/podcast_studio_handoff/`（README + 01–09，共 10 份，已全文阅读，保持原样作为 immutable baseline）
- 现状（2026-10-18 注）：这是接手时的评估，保留原文作记录；当前状态看 `PROJECT_STATUS.md` 和 `docs/status/`，后续决策看 `DECISIONS.md` 与 `docs/decisions/`。
- 状态：**方向已确认（2026-10-16）**：路径 A 与 MVP 收窄已同意；历史 raw 录音已不存在（见 `DECISIONS.md` D26/D27，S4 取消，第 4.9 条与 S5 的评测方式随之改变）；硬件约束见 `HARDWARE_PROFILE.md`。本文档不改变 Handoff 中任何 CONFIRMED 决策，只做审计、补充和提议。

---

## 1. 我对产品的理解（一段话版）

LACUNA 是一个本地运行（Windows + macOS）、浏览器访问 localhost 的 **AI Podcast Producer**，服务于双主持人中文电影播客《洛城二三事》。输入是 Riverside 的两条分轨原始录音（约 2h）和用户自己提供的音乐 / 电影台词素材；AI 先理解整集，再在**只使用原始录音、不增加任何一个字**的前提下做非破坏性剪辑（口误、死气、坏打断、无价值絮叨、音量），并做音效设计（系列片头、过场主题曲、低音量垫乐、台词插入）。用户的工作是：给方向、完整听一遍成品（1×/1.5×）、在播放点直接用中文说“这里恢复一下 / 停顿短一点”，AI 局部渲染预览 → 用户批准 → 提交。目标是 2h 原始素材的人工投入 1–2h、上限 3h，基本不再手动做波形级剪辑。

核心原则：**Preserve the conversation. Polish the delivery. Remove awkwardness, not personality.**

## 2. Context integrity check（Handoff 验收清单）

| 检查项 | 结论 |
|---|---|
| 云端 / 多用户 / R2/S3 方案已被**取代**（D02） | ✅ 认可，V1 不做任何云端部署和素材上传 |
| Windows（Leon）+ macOS（搭档）同一代码库、各自独立安装（D03） | ✅ |
| 不新增任何词、不做语音生成 / 克隆（D08） | ✅ 并且我建议在架构层面**让“编造”在结构上不可能**（见 §6） |
| 自然口语优先，保留重复强调、犹豫、笑声、跑题、原始顺序（D06/D07） | ✅ |
| 素材只用用户提供的；AI 管理文件夹、元数据、处理（D13） | ✅ |
| 音效设计自主度灵活，不搞 A/B/C 模式（D12） | ✅ |
| 局部预览 → 批准 → 提交，不每次全量重渲染；整集听 + 改动审阅都必须有（D15/D16） | ✅ |
| 1–2h 人工、3h 上限、近乎零手工微剪（D18） | ✅ 注意：整集 1.5× 收听本身就要约 60 分钟（见 §4.7） |
| Claude 个人订阅集成**未验证**（D01） | ✅ 已在本次核实，结论见 §3 |
| 持久化状态 / 决策文档 | 已建 `docs/`，代码仓库建立后迁入（见 §9） |

## 3. Gate 0 结论：产品运行时能否用 Max 订阅、且无额外 API 计费？

**结论：CONDITIONAL GO —— 有一条官方明确支持、且不会产生意外扣费的路径，但它不是“用 Claude Code 订阅登录”，而是 Max 计划自带的每月 API 额度。**

### 3.1 官方文档原文要点（2026-10-16 查阅）

1. **订阅 OAuth 不能用于自建应用。** Claude Code《Legal and compliance》：OAuth 认证“is intended exclusively for purchasers of Claude Free, Pro, Max, Team, and Enterprise subscription plans and is designed to support ordinary use of Claude Code and other native Anthropic applications”；“Developers building products or services that interact with Claude's capabilities, including those using the Agent SDK, should use API key authentication… Anthropic does not permit third-party developers to offer Claude.ai login into their own applications, or to route requests through Free, Pro, or Max plan credentials on behalf of their users.”并注明 Anthropic 可不经通知执行限制。
   来源：https://code.claude.com/docs/en/legal-and-compliance
2. **Agent SDK 文档同样写明**：“Unless previously approved, Anthropic does not allow third party developers to offer claude.ai login or rate limits for their products, including agents built on the Claude Agent SDK. Use the API key authentication methods…”
   来源：https://code.claude.com/docs/en/agent-sdk
3. **Consumer Terms §3** 禁止“to access the Services through automated or non-human means, whether through a bot, script, or otherwise”，例外是“via an Anthropic API Key or where we otherwise explicitly permit it”。
   来源：https://www.anthropic.com/legal/consumer-terms
4. `claude setup-token` 生成的一年期 OAuth token（`CLAUDE_CODE_OAUTH_TOKEN`）官方说明用于“CI pipelines, scripts”，但它仍是 Claude Code 的认证方式，受上面第 1 条约束——**让 LACUNA 在后台用它驱动 `claude -p` 来做产品功能，属于灰色地带**，尤其当搭档也安装使用时，就是“把 claude.ai 登录接入自己的应用”。
   来源：https://code.claude.com/docs/en/authentication
5. **Max 计划自带每月 API 额度**（这是关键）：Max 5x 每月 **$100**，Max 20x 每月 $200。在 claude.ai「Settings > Billing → API credits」把一个 Claude Console organization 链接到订阅即可领取；**不需要绑定银行卡**；可用于 “Claude API, Claude Managed Agents, the Claude Agent SDK, and playground”；**不能**用于 Claude Code 本身；每月过期不结转；**额度用完时 “API requests stop until your next monthly API credits arrive. Usage is never charged to your Claude plan.”** 只有手动购买额度或开启 auto-reload 才会继续扣费。新订阅需满 7 天。
   来源：https://platform.claude.com/docs/en/about-claude/api-credits-for-subscribers ，https://support.claude.com/en/articles/17154008-api-credits-for-max-and-team-plans
6. 另：订阅的 5 小时 / 每周限额由 Claude 与 Claude Code 共享（https://support.claude.com/en/articles/11145838-use-claude-code-with-your-pro-or-max-plan）。走 API 额度**不占用**这些限额，也就是说 LACUNA 运行不会挤占你日常用 Claude / 我开发时用的额度。

### 3.2 三条可选路径

| 路径 | 合规性 | 费用风险 | 体验 | 建议 |
|---|---|---|---|---|
| **A. Max 自带 $100/月 API 额度 + Console API key**（Anthropic SDK 直接调 Messages API，Opus 5.5） | 官方明确支持 | 不绑卡、不开 auto-reload 时为**硬上限**，用完即停，零意外账单 | 最好：完全集成在 LACUNA 里，可做结构化输出、缓存、Batch | **推荐** |
| B. 后台用订阅登录的 Claude Code CLI（`claude -p` / Agent SDK + OAuth） | 灰色，文档明确不允许第三方应用路由订阅凭据；可能被执法 | 无账单，但有被限制 / 封号的风险 | 好 | 不推荐 |
| C. LACUNA 只提供工具（MCP server + skills），由你在自己的 Claude Code 里**交互式**使用 | 属于 “ordinary use of Claude Code”，合规 | 占订阅限额 | 聊天在终端 / Claude 桌面端，与播放器分离，体验明显变差 | 作为备用通道保留 |

### 3.3 $100/月够不够？（估算，Spike 中实测）

Opus 5.5 API 价格：输入 $4 / MTok，输出 $20 / MTok，缓存命中 $0.20 / MTok，Batch 半价（https://platform.claude.com/docs/en/about-claude/pricing）。

2h 中文对话约 3 万字，带 ID / 时间戳 / 声学特征标注后约 8–12 万 token。粗估一集：整集理解 ≈ $0.7；按话题段做剪辑决策（共享缓存的整集上下文）≈ $2–4；对话式修改 50 次 ≈ $2–3；节目文案 / 章节 ≈ $0.5。**合计约 $5–10 / 集**，每月 4 集远低于 $100。历史 10 集学习是一次性成本，可用 Batch 降到约一半。这些是估算，Spike S1 会用真实 token 计数校准。

### 3.4 结论对产品的影响

- “用 Claude Code 驱动产品”这个原假设（D01 中的 integration 部分）需要**改为“用 Claude API（Max 赠送额度）驱动产品，用 Claude Code 驱动开发”**。模型偏好（Opus 5.5）、“无额外付费”目标都能满足。
- 搭档（Mac）如果没有 Max 5x/20x，就没有赠送额度，需要自己的付费 API key，或只能用无 AI 模式。这是 Phase 6 前需要定的事，不阻塞现在。
- 本地优先的边界需要写清楚：**音频与素材永远不离开本机；发给 Anthropic API 的只有转写文本和数值化的声学特征**（API 数据适用 Commercial Terms）。

## 4. 矛盾、缺口与隐含假设

1. **“AI 听音频判断韵律”与模型能力不符。** Claude Messages API 的输入类型是 text / image / document 等，**没有音频输入**（已查 API reference）。Playbook 要求“Judge with audio prosody and surrounding context, not text alone”。这意味着“AI 听”必须由本地信号处理来实现：停顿时长、语速、能量、音高轮廓、笑声 / 叹气等事件检测、两轨重叠，序列化成文本特征交给 Claude。这是整个产品质量的天花板所在，Handoff 里没有显式说明。
2. **音乐“情绪契合”同理。** AI 不能真正“听”配乐。可以本地提取能量曲线、段落结构、节拍、渐强 / 收尾点，加上曲目元数据和 Claude 对电影本身的知识来提 2–3 个候选片段，**最终“好不好听”由你听预览决定**。Journey 2 里“AI analyzes emotional fit”应降级为“AI 基于结构分析给候选，用户试听选择”。
3. **ASR 是否保留口误是隐藏的头号技术风险。** Whisper 系模型会习惯性“顺掉”嗯、呃、重复和半截话——恰恰是我们要识别的东西。如果转写把“我觉得这个电影吧，就是……怎么说呢，我觉得它的这个故事，呃，故事”转成通顺句子，后面的剪辑判断全部失真。必须做中文逐字（verbatim）ASR 对比（FunASR Paraformer / SenseVoice / Whisper large-v3 / whisper.cpp 等）。
4. **“剪辑点精度”文档没覆盖。** ASR 字级时间戳误差常在 50–150ms，直接在这些点剪会切掉字头字尾。需要在候选边界附近用能量谷 / 过零点 / VAD 二次精修，并加短交叉淡化与 room tone 填充。
5. **插话“后移”依赖串音（bleed）程度。** 如果 A 的麦克风里有 B 的声音，把 A 轨的“对对对”挪后会产生回声。需要在真实素材上测 bleed，必要时只在 A 轨该片段两侧做门限处理。
6. **自主度的默认策略缺失。** D12/D17 说不要固定模式，Open Questions 又把“高影响内容删除的自动应用标准”延后。但第一刀必须有默认策略。我的默认（可随时改）：机械性清理（口误、死气、轻微重叠）直接应用并按类分组汇总；**内容删除超过约 15 秒、插话移动 / 删除**也在第一刀中应用，但全部标记为“需过目”并排在 Edit Review 最前面；低置信度的一律保留原样并标注。这符合 D11 “先出第一刀再审阅”。
7. **人工时间预算偏紧，需要被设计出来。** 2h 原始 → 成品约 90 分钟 → 1.5× 整听约 60 分钟。所以 Edit Review + 音效 + 发布材料必须压在 30–60 分钟以内。这决定了 Edit Review 必须做“风险排序 + 分组”，而不是逐条审批；并且 Full Listen 过程中的即时反馈要能直接替代一部分 Edit Review。
8. **“整集听”与“不全量重渲染”需要一个具体机制。** 我的方案：按话题段（约 3–8 分钟）分段渲染缓存，修改只让受影响的段失效重渲；播放器无缝串接分段。整集最终母带只在导出时渲染。
9. **历史数据应该更早用。** Roadmap 把历史 raw/final 学习放在 Phase 5（个性化）。但这 10 集是**唯一能客观衡量“AI 剪得像不像你”的地面真值**。我建议 Phase 1 就对 1–2 集做对齐，作为第一刀质量的评测集；“推断偏好规则”这个功能可以晚做，但评测必须早做。
10. **跨平台测试的现实。** 我在 Linux 云环境开发，不能直接在你的 Windows 或搭档的 Mac 上点按。方案：GitHub Actions 的 windows / macos runner 跑自动化测试 + 打包冒烟测试；真实硬件性能（GPU、Apple Silicon 转写速度）需要你在自己机器上跑一次基准脚本（我写好，一条命令）。这是你唯一需要“动手”的 QA 环节，且只做少数几次。
11. **小问题**：产品名 Handoff 中为“AI-Native Podcast Studio”，现定为 LACUNA Studio；Riverside 导出格式（WAV/48k？每轨是否从会话开始对齐）需在第一份素材上确认；喜马拉雅自动发布保持 Phase 6 再查。

## 5. 主要技术风险（按严重度排序）

| # | 风险 | 影响 | 验证方式 |
|---|---|---|---|
| R1 | **第一刀的编辑品味**：Claude 仅凭文本 + 声学特征能否做出“像 Leon 的”取舍，尤其是保留自然重复 vs 删除口误 | 产品成立与否 | S5：15 分钟片段，AI 剪辑计划 vs 你真实成品对比 + 你盲听打分 |
| R2 | 中文逐字 ASR：口误 / 填充词 / 半截字保留率，人名片名，时间戳精度 | R1 的输入质量 | S2：多引擎对比，人工标注 5 分钟金标准（我来标，你抽查 1 分钟即可） |
| R3 | 剪辑点音质：切字、呼吸断裂、底噪跳变、咔哒声 | 成品可听性 | S3：自动检测（点击/能量跳变）+ A/B 片段由你听 |
| R4 | 跨平台打包：Python + ML 模型 + FFmpeg 在 Windows / Apple Silicon / CPU-only 上安装与性能 | 搭档能否用、安装体验 | S6：CI 矩阵 + 你机器跑基准 |
| R5 | 历史成品对齐精度（成品叠了音乐、做了响度处理） | 评测与学习 | S4：1 集 raw/final 对齐报告 |
| R6 | API 额度消耗 | 成本 | S1：真实 token 计数 |
| R7 | 长任务可靠性：重启恢复、文件半拷贝、缓存失效 | 数据安全 | 单元 + 集成测试，设计阶段即覆盖 |

## 6. 架构提案（假设，Spike 后定稿）

```
Browser (localhost, React + TS + Vite)
   │  REST + WebSocket（任务进度、聊天流）
Local backend (Python 3.12, FastAPI, 仅绑定 127.0.0.1)
   ├─ Project store：SQLite (WAL) + append-only EDL op log + 原始素材 content hash / 稳定 media ID
   ├─ Job engine：持久化任务 DAG（进程内，无 Redis/Celery），幂等、可恢复、缺素材只阻塞下游
   ├─ Audio engine：FFmpeg（解码/编码/响度）+ numpy 精确拼接、交叉淡化、room tone、ducking；分段渲染缓存
   ├─ Analysis：ASR（S2 选型）+ VAD + 声学特征 + 事件检测（笑声等）+ 两轨重叠分析
   ├─ AI adapter：Anthropic Python SDK → Messages API（Opus 5.5 主力，Haiku/Sonnet 做廉价标注）；
   │             record/replay 模式供测试，零成本、可重复
   └─ Asset inbox：文件夹监听（防抖 + 文件稳定检查）、自动索引元数据
Local workspace（用户可配置）：raw/ history/ assets/ inbox/ projects/ exports/ cache/
```

关键设计决定：

- **编辑语言只引用源素材 ID，不接受文本。** Claude 输出的是 `{op: cut, track: B, from: tok_1832, to: tok_1840, reason, confidence}` 这样的操作，渲染器只会拼接原始音频区间。任何“改写文本”在结构上无法变成音频，D08 从“靠提示词约束”变成“靠架构保证”。
- **两轨永不提前混成一轨。** 每个操作带轨道和来源区间，满足 provenance 与可逆。
- **直接用 Messages API 而不是 Agent SDK。** 我们不需要让模型读写文件或跑命令；结构化输出 + 我们自己的工具定义更可控、更好测、更便宜。
- **ASR 后端可插拔**：Windows NVIDIA（CUDA）/ Apple Silicon（Metal/MLX）/ CPU 回退，按 S2/S6 实测选择。
- **V1 打包**：一键安装脚本（PowerShell / bash），用 `uv` 管 Python 环境，附带 FFmpeg，启动后自动打开浏览器。原生壳（Tauri）推迟。
- **数据安全**：原始文件只读、原子写、自动备份项目库、导出路径防覆盖、仅 loopback、路径与文件名注入防护。

## 7. 实施路线（建议）

| 阶段 | 内容 | 并行性 | 出口 |
|---|---|---|---|
| **P0 交接持久化** | 建仓库，`CLAUDE.md`、`docs/DECISIONS.md`、`PROJECT_STATUS.md`、`OPEN_QUESTIONS.md`、`ARCHITECTURE.md`、`TEST_PLAN.md`；Handoff 原件入 `docs/handoff/` | — | 新会话可无缝接手 |
| **P1 技术 Spikes** | S1 API 额度桥接与 token 计量；S2 中文逐字 ASR 对比；S3 双轨 EDL + 渲染 + 剪辑点质量 + 局部预览；S4 历史 raw/final 对齐；S5 **AI 第一刀质量评测**（依赖 S2+S4）；S6 跨平台安装与性能基准 | S1/S2/S3/S4/S6 可由并行 Agent 同时做 | 可行性报告 + 架构 ADR，GO/NO-GO |
| **P2 UX** | 旅程图、信息架构、低保真线框（Setup / Episode Workspace / Full Listen / Edit Review / Asset Inbox / Playbook），然后可点击原型（标明 mock 数据） | **与 P1 并行**，不依赖技术结论 | 你确认主旅程（只看交互，不看像素） |
| **P3 核心垂直切片** | 15 分钟真实片段跑通：导入 → 整集理解 → 第一刀 → Full Listen + Edit Review → 播放点聊天修改 → 局部预览 → 批准提交 → 撤销 → 导出；然后扩到整集 | — | 你不打开 Audacity 就能完成一次审阅 |
| **P4 编排与音效** | 任务 DAG、素材收件箱、系列片头规则、配乐候选与 ducking、台词片段插入 | — | 缺素材不阻塞其他工作 |
| **P5 个性化** | 批量历史对齐、候选偏好规则、审批与版本、held-out 评测 | — | 误删率可度量地下降 |
| **P6 发布与打包** | 母带、章节、show notes、喜马拉雅辅助上传包；Windows/macOS 安装、升级、搭档交付 | — | 搭档在 Mac 上独立跑通 |
| **P7 真实整集验收** | 完整 2h 集，记录人工时间 / 机器时间 / 审批量 / 问题 | — | 人工 ≤ 3h |

与 Handoff Roadmap 的差异只有三点：P2 与 P1 并行；历史对齐提前进 P1 作为评测基础；新增 S5“第一刀质量”作为真正的产品 Go/No-Go。

**AI-native 开发方式**：Spikes 和后续模块用并行 Agent（独立 worktree）实现，每个 Agent 交付代码 + 测试 + 证据；我负责集成、评审和最终质量。测试策略按 Handoff 06 的 7 层执行，音频用合成双轨 golden fixtures，AI 调用用 record/replay，UI 用 Playwright，CI 跑三平台。

## 8. 决策分类

### 8.1 直接继承（不再讨论）
D02–D19、D21、D22 全部继承；Editorial Playbook 全文作为编辑宪法；V1 非目标清单全部继承。

### 8.2 需要技术验证（我负责，结果会回报）
- D01 的集成方式（已初步核实，S1 实测）
- D05 前端具体栈；整体后端栈（§6 为假设）
- ASR 引擎与加速后端（S2/S6）
- 剪辑点质量、插话移动可行性（S3）
- raw/final 对齐精度（S4）
- AI 第一刀能否达到可用品味（S5）
- D20 喜马拉雅 API / 自动化（P6）

### 8.3 我自主决定（会记录在 DECISIONS.md，不打扰你）
第一刀自主度默认策略（§4.6）、分段渲染缓存、编辑语言设计、播放器细节、测试与 CI、目录结构、模型分工（Opus 主力，便宜模型做批量标注）。

### 8.4 需要 Leon 决定
1. **AI 运行时走路径 A（Max 自带 $100/月 API 额度）**？如同意，请在 claude.ai「Settings → Billing → API credits」链接一个 Console organization，**不要绑卡、不要开 auto-reload**，然后在 Console 建一个 API key 给 LACUNA（key 只存在你本机，不发给我；开发阶段我用 mock/replay 或你单独给的开发 key）。
2. **MVP 范围收窄**：MVP = 人声剪辑 + 审阅闭环 + 导出 + 系列片头规则 + 用户手动指定配乐的放置与 ducking；把“AI 主动推荐配乐片段”“推断偏好规则”“喜马拉雅自动化”放到 MVP 之后。是否同意？
3. （不急，P6 前定）搭档 Mac 的 AI 费用：搭档是否有 Max 5x/20x？没有的话是自付 API 还是只用无 AI 功能。

### 8.5 开始 Spike 需要的输入（不是决策）
- 一段 10–15 分钟的真实 Riverside 双轨原始录音（两个文件）。
- 1–2 集历史的 **双轨原始 + 你剪好的成品**（整集），用于对齐与评测；有最好是同一集里包含插话处理和配乐的。
- 你的 Windows 机器配置（CPU、内存、有无 NVIDIA 显卡及型号），搭档 Mac 型号（M 系列？）。
- 连接 GitHub（https://claude.ai/connect-github）并新建一个私有仓库（例如 `lacuna`），我把文档和代码放进去。

## 9. 持久化计划

仓库建立前，项目文件暂存于 `/mnt/project-files/lacuna/`：
- `handoff/`：Handoff 原件（不修改）
- `docs/00_TECH_LEAD_ASSESSMENT.md`：本文档
- `docs/PROJECT_STATUS.md`：当前状态与下一步

仓库建立后按 Handoff 09 迁入 `docs/handoff/`、`CLAUDE.md`、`docs/DECISIONS.md` 等，并在每次会话结束更新 `PROJECT_STATUS.md`。
