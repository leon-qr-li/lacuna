# 公开 beta 之前的待办（发邀请给外部用户之前）

Leon 要求记下的、正式商业化 / 发 beta 邀请前必须做完的事。新的条目加在「最后一步」之前；「最后一步」永远排在最后。

## 待办
- [ ] **正式发布前撤回公开的 `/api/version`，换成最安全的版本校验方式**（Leon 2026-10-20：「在正式发布前，我要撤回，要最安全的方式」）。
  - 现在：`lacunastudio.app/api/version` 和 staging 上的同一地址不用登录就能打开，只返回版本号，部署校验靠它（`docs/decisions/2026-10-20-public-version-check.md`）。
  - 撤回时：删掉 `deploy/provision.py` 的 `version_door` 和两个 Access 应用「LACUNA version」「LACUNA preview version」及策略「LACUNA version (public)」（跑 Provision apply 不会自动删，要用 API 删掉），删掉 `lacuna_app/cloud.py` 的 `VERSION_PATH` 放行；部署校验改用一个长期 Access service token（存 GitHub secret，门完全关上），`deploy/ci.py wait_live` 带上它读 `/api/health`。

## 最后一步（发 beta 邀请之前，Leon 2026-10-19 定）
- [ ] **彻底再测一遍英文剪辑的水平：精度测试 + 深度测试。**
  - 素材：至少几集真实的英文播客，最好是每人一条分轨（Riverside 那种）、加上真人剪好的成品，类型覆盖 2 人 / 3 人以上、访谈 / 闲聊、口音不同。来源：beta 候选用户或公开分轨数据集（需要云端环境放行 huggingface.co 等）。
  - 精度：英文识别错字率；um / uh 找回率和误报率（要有人工标注作对照，2026-10-19 的 spike 没有标注，只量了误报）；AI 第一刀和真人剪辑的吻合度（用 S4/S5 的打分方式：剪对、剪多、漏剪、该保留的被删）。
  - 深度：整集 1-2 小时的速度和云端资源占用；多人串话、笑声、背景音乐；长停顿收紧是否自然；审阅页和导出成品逐段听。
  - 结论写成报告，按结果校准英文剪辑要求（`prompts/first_cut_brief_en.txt`、`first_cut_defaults_en.txt`）后再发邀请。
  - 起点：`docs/status/english-engine.md`、`/mnt/project-files/lacuna/docs/英文剪辑实测_2026-10-19.md`。
