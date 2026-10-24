// Names for the codes the admin API sends (statuses, events, sources, plans ...), in the interface language.
import { t } from "./i18n";
import type { FbStatus } from "./types";

export const FB_STATUS: Record<FbStatus, { label: () => string; tone: "" | "ok" | "warn" | "info" | "acc" }> = {
  received: { label: () => t("新"), tone: "acc" },
  working: { label: () => t("处理中"), tone: "warn" },
  planned: { label: () => t("在计划中"), tone: "info" },
  fixed: { label: () => t("已修好"), tone: "ok" },
  shipped: { label: () => t("已上线"), tone: "ok" },
  declined: { label: () => t("暂不做"), tone: "" },
};

export const FB_KIND: Record<string, () => string> = {
  bug: () => t("问题"),
  idea: () => t("建议"),
  praise: () => t("夸一句"),
};

export const ROLE: Record<string, () => string> = {
  owner: () => t("站长"),
  admin: () => t("管理员"),
  member: () => t("成员"),
};

export const PLAN: Record<string, () => string> = {
  trial: () => t("免费体验"),
  basic: () => t("基础版"),
  pro: () => t("专业版"),
};
export const planName = (p: string | null | undefined) => (p && PLAN[p] ? PLAN[p]() : p || "—");

export const SOURCE: Record<string, () => string> = {
  xiaoyuzhou: () => t("小宇宙"),
  friend: () => t("朋友介绍"),
  survey: () => t("问卷"),
  request: () => t("申请试用"),
  pei: () => t("Pei 介绍"),
  other: () => t("其他"),
  invited: () => t("邀请"),
};
export const sourceName = (s: string | null | undefined) => (s && SOURCE[s] ? SOURCE[s]() : s || "—");

export const TRACKS: Record<string, () => string> = {
  separate: () => t("每人一条分轨"),
  mixed: () => t("混在一条"),
  unsure: () => t("不确定"),
};

/** What an event in the log means, in a few words. */
export const EVENT: Record<string, () => string> = {
  "user.signup": () => t("注册了"),
  "user.login": () => t("登录了"),
  "import.start": () => t("开始导入"),
  "import.done": () => t("导入完成"),
  "import.error": () => t("导入失败"),
  "import.interrupted": () => t("导入中断"),
  "import.cancelled": () => t("取消了导入"),
  "export.start": () => t("导出了"),
  "show.create": () => t("建了节目"),
  "show.invite": () => t("邀请了搭档"),
  "invite.send": () => t("发了邀请"),
  "publish.generate": () => t("生成了发布资料"),
  "publish.save": () => t("保存了发布资料"),
  "poster.generate": () => t("生成了海报"),
  "poster.choose": () => t("选了海报"),
  "chat.message": () => t("用对话改了剪辑"),
  "chat.approve": () => t("批准了对话修改"),
  "review.decide": () => t("审阅了一处改动"),
  "review.batch": () => t("批量审阅"),
  "edit.manual": () => t("手动剪辑"),
  "music.auto": () => t("自动配乐"),
  "music.add": () => t("加了配乐"),
  "levels.auto": () => t("统一了音量"),
  "rule.remember": () => t("记住了一条规则"),
  "lessons.run": () => t("总结学到的规则"),
  feedback: () => t("提交了反馈"),
  "request.trial": () => t("申请试用"),
  "request.collab": () => t("搭档申请"),
};
export const eventName = (ev: string) => (EVENT[ev] ? EVENT[ev]() : ev);

/** The admin's own actions in the audit log. */
export const ACTION: Record<string, () => string> = {
  "admin.login": () => t("登录后台"),
  "admin.stepup": () => t("输入验证码"),
  "admin.sessions.end": () => t("退出后台登录"),
  "feedback.reply": () => t("回复 / 处理反馈"),
  "feedback.tags": () => t("改反馈标签"),
  "feedback.prompt_reset": () => t("重置「一题」"),
  "templates.save": () => t("改回复模板"),
  "note.add": () => t("写备注"),
  "user.update": () => t("改账号"),
  "user.delete": () => t("删除账号"),
  "user.erase": () => t("立即彻底删除账号"),
  "user.mail": () => t("发邮件"),
  "user.sessions.end": () => t("退出对方所有登录"),
  "hours.give": () => t("加时长"),
  "hours.approve": () => t("批准加时长"),
  "hours.decline": () => t("拒绝加时长"),
  "beta.end": () => t("改 beta 截止日"),
  "beta.seats": () => t("改 beta 名额"),
  "site.new_members": () => t("新成员需站长批准"),
  "site.notice": () => t("站内公告"),
  "site.maintenance": () => t("维护模式"),
  "site.terms": () => t("系统专有名词"),
  "mail.test": () => t("发测试信"),
  "staff.role": () => t("改管理员"),
  "invite.send": () => t("发邀请"),
  "invite.resend": () => t("重发邀请"),
  "invite.revoke": () => t("撤回邀请"),
  "request.invite": () => t("批准申请并邀请"),
  "request.dismiss": () => t("忽略申请"),
  "request.waitlist": () => t("申请进等候名单"),
  "show.open": () => t("打开节目（排查）"),
  "trash.restore.show": () => t("恢复节目"),
  "trash.restore.user": () => t("恢复账号"),
  "trash.purge.show": () => t("彻底清除节目"),
  "trash.purge.user": () => t("彻底清除账号"),
  "ai.budget": () => t("改 AI 预算"),
};
export const actionName = (a: string) => (ACTION[a] ? ACTION[a]() : a);

export const FEATURE: Record<string, () => string> = {
  first_cut: () => t("初剪"),
  chat: () => t("对话修改"),
  notes: () => t("Show notes"),
  poster: () => t("海报"),
  rules: () => t("学到的规则"),
  music: () => t("配乐"),
  levels: () => t("统一音量"),
  coedit: () => t("多人协作"),
};
export const featureName = (f: string) => (FEATURE[f] ? FEATURE[f]() : f);

export const STEP: Record<string, () => string> = {
  "import.start": () => t("导入"),
  "import.done": () => t("初剪完成"),
  review: () => t("审阅"),
  "export.start": () => t("导出"),
  "publish.generate": () => t("发布资料"),
};

export const REGION: Record<string, () => string> = {
  na: () => t("北美"),
  eu: () => t("欧洲"),
  oceania: () => t("澳新"),
  asia: () => t("亚洲其他地区"),
  cn: () => t("中国大陆"),
};
export const EDITING: Record<string, () => string> = {
  self: () => t("自己剪"),
  hired: () => t("请人剪"),
  none: () => t("基本不剪"),
  new: () => t("刚开始做"),
};
export const PMF: Record<string, () => string> = {
  very: () => t("非常失望"),
  somewhat: () => t("有点失望"),
  not: () => t("无所谓"),
};
export const SAVED: Record<string, () => string> = {
  none: () => t("没省"),
  half: () => t("半小时内"),
  "1-2h": () => t("1–2 小时"),
  "2h+": () => t("2 小时以上"),
  never: () => t("以前不剪"),
};
export const PART: Record<string, () => string> = {
  raw: () => t("原始音轨"),
  episodes: () => t("剧集文件"),
  exports: () => t("导出文件"),
  music: () => t("配乐库"),
  trash: () => t("回收区"),
  other: () => t("其他"),
};
export const CATEGORY: Record<string, () => string> = {
  pause: () => t("停顿收紧"),
  filler: () => t("口误与无意识重复"),
  crosstalk: () => t("单轨杂声"),
  single_track: () => t("单轨删减"),
  content: () => t("内容删除"),
  interjection: () => t("插话处理"),
  other: () => t("其他"),
};
export const PLATFORM: Record<string, string> = {
  apple: "Apple Podcasts",
  spotify: "Spotify",
  youtube: "YouTube",
  amazon: "Amazon Music",
};
