# 公开 beta 之前的待办（发邀请给外部用户之前）

Leon 要求记下的、正式商业化 / 发 beta 邀请前必须做完的事。新的条目加在「最后一步」之前；「最后一步」永远排在最后。

## 待办
- [x] **正式发布前撤回公开的 `/api/version`，换成最安全的版本校验方式**（Leon 2026-10-20：「在正式发布前，我要撤回，要最安全的方式」）。
  - 现在：`lacunastudio.app/api/version` 和 staging 上的同一地址不用登录就能打开，只返回版本号，部署校验靠它（`docs/decisions/2026-10-20-public-version-check.md`）。
  - 撤回时：删掉 `deploy/provision.py` 的 `version_door` 和两个 Access 应用「LACUNA version」「LACUNA preview version」及策略「LACUNA version (public)」（跑 Provision apply 不会自动删，要用 API 删掉），删掉 `lacuna_app/cloud.py` 的 `VERSION_PATH` 放行；部署校验改用一个长期 Access service token（存 GitHub secret，门完全关上），`deploy/ci.py wait_live` 带上它读 `/api/health`。
  - **第五批已做（2026-10-25，Leon 打字同意）**：代码里全部撤掉，`docs/decisions/2026-10-25-withdraw-public-version.md`。跑一次 Provision apply 删掉 Access 上的门，再跑 Provision `deploy-token` 把长期令牌存成 GitHub secret 才算上线（`docs/status/batch-5.md`）。

- [ ] **AI 全包进订阅价 + 每月音频小时额度（方案 B，大项，必须做）**（Leon 2026-10-20：「在上线之前做，这是一个大方案，必须做」；`docs/decisions/2026-10-20-ai-included-hour-quota.md`）。
  - 每个工作区每月可处理的音频小时数（暂定 Creator 4 小时、Pro 12 小时），导入时检查；界面显示「本月已用 x / y 小时」，用完给明确提示。
  - Console 组织设每月 AI 总花费上限，作为第二道保险。
  - 降成本（每项先做质量对比再换）：初剪走 Batch API、对话从 Opus 5.5 换 Sonnet 5.5、小任务用 Haiku 5.5、对话加提示缓存。目标每小时音频 AI 成本从约 $3.3 降到约 $1.8。
  - 邀请内测用户之前至少先有每人上限（现在代码里没有）。
  - **第五批已做（2026-10-25）**：计量和每人每月额度（`docs/decisions/2026-10-24-hour-metering.md`）；对话提示缓存；Batch 是后台开关、默认关。盲比后质量优先：对话留 Opus，经验总结和查曲名换回原模型（PR #204），Leon 2026-10-25 定「不换，质量优先」，等 beta 真实数据再说（`docs/decisions/2026-10-25-ai-cost-cut.md`）。还剩：Console 月度总花费上限（Leon 在 Console 设）。
  - 以后再加：超额加购包（方案 C，约 $5 / 2 小时），和接支付平台一起做。
- [ ] **完整的 admin 平台（App 管理后台）：上线前做（Leon 2026-10-20）。** 把现在散在设置里的成员与邀请、邮件、AI 密钥、系统专有名词、项目总览集中管理。
- [ ] **权限重新梳理与设计：上线前做（Leon 2026-10-20）。** 分层：订阅套餐（basic / professional 等，和 AI 额度方案 B 对应）+ 角色（网站管理员；项目里的管理员 / 剪辑师 / 只读）。
- [ ] **服务器硬盘方案 + 上线前压力测试（硬盘方案第五批已定已做：冷热分层 + 数据盘 100 GB + staging 硬链接 + 只留最新导出，`docs/decisions/2026-10-25-audio-cold-storage.md`；压力测试还没做）（Leon 2026-10-20：「现在先不改，上线前要做决策……上线前我们要 hammering this thing」）。**
  - 实测（2026-10-20 23:48Z，DO 监控）：数据盘 `/data` 共 52.5 GB，已用约 6.2 GB；系统盘 160 GB 几乎全空。一集约 2 GB，staging 再复制一份，约 4 GB。
  - 让 Leon 选的方案：① staging 改用硬链接共用音频（音频只读，加测试，推荐）；② staging 放到系统盘（先确认是否加密）；③ 每集只留最新一份导出 WAV；④ 删测试集（要他打字确认）；或者数据盘扩到 250 GB（+$20/月，见 `/mnt/project-files/lacuna/docs/服务器容量与扩容预算_2026-10-20.md`）。
  - 压力测试：多集同时上传 / 导入 / 导出、硬盘接近写满、自动更新撞上正在进行的任务；看会不会掉线、丢数据，满了以后提示是否清楚。
  - 在这之前：每小时巡检会读硬盘，用到 70% 就告诉 Leon。
- [ ] **发 beta 邀请前提醒 Leon 把 AI 等付费服务的钱充好，并按预算做准备**（Leon 2026-10-25：「做 beta 之前要提醒我把什么 AI 呀、这些该充的值都充好了，多少预算做个准备」）。
  - 模型按「质量优先」（`docs/decisions/2026-10-25-ai-cost-cut.md`：对话 Opus、经验总结 Sonnet、查曲名 Opus，第一刀 Batch 开关保持关）。PULSE-013 实测单价折算每小时音频 AI 约 $3.8（少改 $3.3，多改 $4.5）；成本与盈利第 2 版 https://claude.ai/artifact/Ht3vYzEQSZBKnY39gyDFD2。
  - Anthropic Console：beta 20 个节目、2 个月，AI 平均约 $380、最多约 $900（总成本含服务器平均约 $532）；Max 每月送 $100 API 额度，建议先充约 $600，开自动充值或余额提醒；同时设好月度总花费上限（见上面方案 B 条目）。后台 AI 预算从 $300 调到 $500（Claude 做）。
  - 其他按月付费的服务也核对一遍余额和付款方式：DigitalOcean 服务器和数据盘、域名、Resend 邮件、Cloudflare。
  - 发邀请时按实际 beta 人数重算预算。

## 最后一步（发 beta 邀请之前，Leon 2026-10-19 定）
- [ ] **彻底再测一遍英文剪辑的水平：精度测试 + 深度测试。**
  - 素材：至少几集真实的英文播客，最好是每人一条分轨（Riverside 那种）、加上真人剪好的成品，类型覆盖 2 人 / 3 人以上、访谈 / 闲聊、口音不同。来源：beta 候选用户或公开分轨数据集（需要云端环境放行 huggingface.co 等）。
  - 精度：英文识别错字率；um / uh 找回率和误报率（要有人工标注作对照，2026-10-19 的 spike 没有标注，只量了误报）；AI 第一刀和真人剪辑的吻合度（用 S4/S5 的打分方式：剪对、剪多、漏剪、该保留的被删）。
  - 深度：整集 1-2 小时的速度和云端资源占用；多人串话、笑声、背景音乐；长停顿收紧是否自然；审阅页和导出成品逐段听。
  - 结论写成报告，按结果校准英文剪辑要求（`prompts/first_cut_brief_en.txt`、`first_cut_defaults_en.txt`）后再发邀请。
  - 起点：`docs/status/english-engine.md`、`/mnt/project-files/lacuna/docs/英文剪辑实测_2026-10-19.md`。
