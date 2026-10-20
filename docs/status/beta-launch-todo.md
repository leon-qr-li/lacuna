# 公开 beta 之前的待办（发邀请给外部用户之前）

Leon 要求记下的、正式商业化 / 发 beta 邀请前必须做完的事。新的条目加在「最后一步」之前；「最后一步」永远排在最后。

## 待办
- [ ] **正式发布前撤回公开的 `/api/version`，换成最安全的版本校验方式**（Leon 2026-10-20：「在正式发布前，我要撤回，要最安全的方式」）。
  - 现在：`lacunastudio.app/api/version` 和 staging 上的同一地址不用登录就能打开，只返回版本号，部署校验靠它（`docs/decisions/2026-10-20-public-version-check.md`）。
  - 撤回时：删掉 `deploy/provision.py` 的 `version_door` 和两个 Access 应用「LACUNA version」「LACUNA preview version」及策略「LACUNA version (public)」（跑 Provision apply 不会自动删，要用 API 删掉），删掉 `lacuna_app/cloud.py` 的 `VERSION_PATH` 放行；部署校验改用一个长期 Access service token（存 GitHub secret，门完全关上），`deploy/ci.py wait_live` 带上它读 `/api/health`。

- [ ] **AI 全包进订阅价 + 每月音频小时额度（方案 B，大项，必须做）**（Leon 2026-10-20：「在上线之前做，这是一个大方案，必须做」；`docs/decisions/2026-10-20-ai-included-hour-quota.md`）。
  - 每个工作区每月可处理的音频小时数（暂定 Creator 4 小时、Pro 12 小时），导入时检查；界面显示「本月已用 x / y 小时」，用完给明确提示。
  - Console 组织设每月 AI 总花费上限，作为第二道保险。
  - 降成本（每项先做质量对比再换）：初剪走 Batch API、对话从 Opus 5.5 换 Sonnet 5.5、小任务用 Haiku 5.5、对话加提示缓存。目标每小时音频 AI 成本从约 $3.3 降到约 $1.8。
  - 邀请内测用户之前至少先有每人上限（现在代码里没有）。
  - 以后再加：超额加购包（方案 C，约 $5 / 2 小时），和接支付平台一起做。
- [ ] **完整的 admin 平台（App 管理后台）：上线前做（Leon 2026-10-20）。** 把现在散在设置里的成员与邀请、邮件、AI 密钥、系统专有名词、项目总览集中管理。
- [ ] **权限重新梳理与设计：上线前做（Leon 2026-10-20）。** 分层：订阅套餐（basic / professional 等，和 AI 额度方案 B 对应）+ 角色（网站管理员；项目里的管理员 / 剪辑师 / 只读）。

## 最后一步（发 beta 邀请之前，Leon 2026-10-19 定）
- [ ] **彻底再测一遍英文剪辑的水平：精度测试 + 深度测试。**
  - 素材：至少几集真实的英文播客，最好是每人一条分轨（Riverside 那种）、加上真人剪好的成品，类型覆盖 2 人 / 3 人以上、访谈 / 闲聊、口音不同。来源：beta 候选用户或公开分轨数据集（需要云端环境放行 huggingface.co 等）。
  - 精度：英文识别错字率；um / uh 找回率和误报率（要有人工标注作对照，2026-10-19 的 spike 没有标注，只量了误报）；AI 第一刀和真人剪辑的吻合度（用 S4/S5 的打分方式：剪对、剪多、漏剪、该保留的被删）。
  - 深度：整集 1-2 小时的速度和云端资源占用；多人串话、笑声、背景音乐；长停顿收紧是否自然；审阅页和导出成品逐段听。
  - 结论写成报告，按结果校准英文剪辑要求（`prompts/first_cut_brief_en.txt`、`first_cut_defaults_en.txt`）后再发邀请。
  - 起点：`docs/status/english-engine.md`、`/mnt/project-files/lacuna/docs/英文剪辑实测_2026-10-19.md`。
