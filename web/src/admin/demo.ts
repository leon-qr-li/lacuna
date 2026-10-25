// 演示数据 (decision 2026-10-24-admin-site): made-up people and numbers that show what every page looks like with a
// few hundred users. Nothing here is real and nothing is ever saved (ui.tsx act() only shows a toast). The
// mock content is data, not interface text, so its Chinese lines carry `i18n-ignore`.
import { t } from "./i18n";
import type {
  AccessData,
  AiData,
  AuditRow,
  FbItem,
  FeedbackData,
  GrowthData,
  HoursData,
  Me,
  Note,
  Overview,
  Prompts,
  SettingsData,
  ShowsData,
  SystemData,
  TrashData,
  UserDetail,
  UserRow,
} from "./types";

const now = () => Math.floor(Date.now() / 1000);
const H = 3600;
const D = 86400;

// a fixed pseudo-random sequence, so the demo looks the same every time
let seed = 7;
const R = () => {
  seed = (seed * 16807) % 2147483647;
  return (seed - 1) / 2147483646;
};
const pick = <T>(a: T[]) => a[Math.floor(R() * a.length)];

const HANDLES = ["chen.podcast", "morning.talk", "huang.y", "kimi.audio", "lisa.w", "film.cast", "nightowl.fm", "two.cities", "bookclub.la", "jasmine.k", "oak.radio", "mapleleaf", "sunset.pod", "tofu.talks", "harbor.show", "ming.z", "cinema.paradiso", "wenwen", "ridge.fm", "slow.radio", "aurora.cast", "tea.time", "mono.no", "kevin.l", "rainy.days", "nyc.chinese", "sydney.yu", "berlin.zh", "ocean.fm", "yuki.s", "lantern.pod", "papercut"];
const DOMS = ["gmail.com", "outlook.com", "icloud.com", "qq.com", "hotmail.com"];
const SHOWS = [
  "深夜电影院", // i18n-ignore
  "两个城市", // i18n-ignore
  "慢读书会", // i18n-ignore
  "海边电台", // i18n-ignore
  "Tea Time Talks",
  "Film Club Weekly",
  "异乡人", // i18n-ignore
  "周末不加班", // i18n-ignore
  "北美生活家", // i18n-ignore
  "Oak Radio",
  "纸上谈影", // i18n-ignore
  "雨天播客", // i18n-ignore
];
const SOURCES = ["xiaoyuzhou", "friend", "survey", "request", "pei"];

let users: UserRow[] | null = null;
function demoUsers(): UserRow[] {
  if (users) return users;
  seed = 7;
  const t0 = now();
  const rows: UserRow[] = [
    {
      email: "leon@example.com",
      name: "Leon",
      role: "owner",
      plan: "pro",
      free: true,
      created: t0 - 60 * D,
      disabled: false,
      twofa: true,
      last: t0 - 2 * H,
      lang: "zh",
      silent: false,
      shows: 2,
      made: 2,
      episodes: 14,
      ai: 31.2,
      size: 18.4e9,
      source: null,
      invited_by: null,
      hours_used: null,
      hours: 12,
    },
  ];
  for (let i = 0; i < HANDLES.length; i++) {
    const h = HANDLES[i];
    const plan = R() < 0.12 ? "pro" : "basic";
    const quota = plan === "pro" ? 12 : 4;
    const lastDays = Math.floor(R() * 24);
    rows.push({
      email: `${h}@${pick(DOMS)}`,
      name: h.split(".")[0],
      role: i === 4 ? "admin" : "member",
      plan,
      free: false,
      created: t0 - Math.floor(5 + R() * 40) * D,
      disabled: R() < 0.05,
      twofa: R() > 0.08,
      last: t0 - lastDays * D - Math.floor(R() * D),
      lang: R() < 0.2 ? "en" : "zh",
      silent: lastDays >= 14,
      shows: 1 + Math.floor(R() * 2),
      made: 1,
      episodes: Math.floor(R() * 14),
      ai: +(R() * 38).toFixed(2),
      size: Math.floor(R() * 9e9),
      source: pick(SOURCES),
      invited_by: "leon@example.com",
      hours_used: +Math.min(quota + 1.5, R() * quota * 1.1).toFixed(1),
      hours: quota,
    });
  }
  users = rows.sort((a, b) => b.ai - a.ai);
  return users;
}

const ME: Me = { email: "leon@example.com", name: "Leon", role: "owner", lang: "zh", exp: now() + 8 * H, stepup: 0, owner: "leon@example.com", now: now() };

const FB: [string, FbItem["kind"], string, string, FbItem["status"], number, string, string[], string | null][] = [
  ["chen.podcast", "bug", "review", "AI 把我故意的停顿剪掉了。那一段是在制造悬念，剪了以后节奏全没了。能不能让我标记「这里别剪」？", "received", 3, "EP12", ["AI 剪错"], "button"], // i18n-ignore
  ["morning.talk", "praise", "review", "英文节目 um/uh 剪得很好，比我自己剪得干净。", "shipped", 5, "EP3", [], "button"], // i18n-ignore
  ["huang.y", "bug", "import", "导入 3 小时的音频排队排了 40 分钟，页面一直显示 0%，我以为卡死了。", "working", 8, "EP7", ["导入"], "error"], // i18n-ignore
  ["kimi.audio", "idea", "show", "希望支持 5 个人以上的圆桌节目。", "received", 12, "", ["圆桌"], "button"], // i18n-ignore
  ["lisa.w", "idea", "publish", "想要自动发到 Apple Podcasts，现在每次都要手动上传。", "received", 14, "", [], "publish"], // i18n-ignore
  ["film.cast", "idea", "poster", "海报风格能不能更简洁一点，有时候字太多。", "planned", 22, "EP9", ["海报"], "button"], // i18n-ignore
  ["nightowl.fm", "bug", "export", "导出 MP3 后声音比预览小一点。", "received", 26, "EP2", [], "button"], // i18n-ignore
  ["two.cities", "bug", "review", "「口头禅」把我搭档的口癖「对吧」剪了太多，有些是有意义的。", "working", 30, "EP8", ["AI 剪错"], "button"], // i18n-ignore
  ["bookclub.la", "idea", "learning", "学到的规则能不能按节目分开？我有两个节目风格不一样。", "received", 33, "", ["学到的规则"], "button"], // i18n-ignore
  ["jasmine.k", "praise", "home", "第一次用就剪完了一集，太爽了。", "fixed", 40, "EP1", [], "button"], // i18n-ignore
  ["mapleleaf", "bug", "review", "英文里 like 被当成口头禅剪了，但那里是动词。", "received", 51, "EP5", ["AI 剪错"], "button"], // i18n-ignore
  ["sunset.pod", "idea", "music", "配乐能不能自己上传更多首？", "declined", 60, "", [], "button"], // i18n-ignore
];

function demoFeedback(): FbItem[] {
  const t0 = now();
  const us = demoUsers();
  return FB.map(([h, kind, page, text, status, hoursAgo, ep, tags, source], i) => {
    const u = us.find((x) => x.email.startsWith(h)) ?? us[1];
    const show = SHOWS[i % SHOWS.length];
    return {
      id: `fb_demo${i}`,
      created: t0 - hoursAgo * H,
      email: u.email,
      kind,
      status,
      unread: status === "received",
      text,
      source,
      shot: false,
      show: { id: `s${i}`, name: show },
      context: {
        page: `/${page}`,
        episode: ep || undefined,
        lang: u.lang ?? "zh",
        browser: i % 3 ? "Chrome · macOS" : "Safari · iPhone",
        error: source === "error" ? "Import failed: queue timeout (504)" : undefined,
        actions: source === "error" ? ["open /import", "choose 3 files", "start import", "wait 40 min"] : undefined,
      },
      importance: kind === "idea" ? (i % 2 ? "need" : "nice") : null,
      quote_ok: kind === "praise" ? true : null,
      platforms: source === "publish" ? ["Apple Podcasts"] : [],
      replies:
        status === "received"
          ? []
          : [{ text: "谢谢！我们已经在看这个问题了，修好了会在这里告诉你。", at: t0 - (hoursAgo - 1) * H }], // i18n-ignore
      adopted: status === "shipped" || status === "fixed",
      bonus_hours: status === "shipped" || status === "fixed" ? 1 : 0,
      version: "a1b2c3d4",
      profile: { region: i % 4 ? "na" : "eu", editing: "self", lang: "zh" },
      name: u.name,
      plan: u.plan,
      joined: u.created,
      tags,
      notes: i === 0 ? 1 : 0,
    };
  });
}

function overview(): Overview {
  const t0 = now();
  const spentCum = Array.from({ length: 24 }, (_, i) => Math.round((i + 1) * 7.6 * 100) / 100);
  return {
    todo: { fb: 6, hours: 3, trial: 4, collab: 1 },
    alerts: [
      {
        level: "warn",
        kind: "capacity",
        measure: "disk",
        line: t("数据盘已用 {pct}%（{used} / {total}）", { pct: 72, used: "72 GB", total: "100 GB" }) + t("，按最近 7 天的速度约 {d} 天后写满", { d: 19 }),
        advice: t("先清回收区；不够就在 DigitalOcean 把数据盘再扩 50–100 GB（在线扩，约 15 分钟，每 100 GB 每月 +$10）。"),
      },
    ],
    kpi: {
      accounts: { value: 186, delta: 12, spark: [120, 131, 140, 151, 160, 168, 174, 186] },
      wau: { value: 97, delta: 6, spark: [61, 66, 72, 78, 84, 88, 91, 97] },
      exports: { value: 142, delta: -8, spark: [96, 104, 121, 133, 128, 141, 150, 142] },
      ai: { value: 182, forecast: 234, budget: 300, spark: spentCum },
      disk: { value: 0.72, used: 72e9, total: 100e9 },
    },
    wau: [61, 66, 72, 78, 84, 88, 91, 97],
    ai: { spent: 182.4, forecast: 234, days: 31, cumulative: spentCum, budget: 300 },
    capacity: [
      { key: "disk", level: "warn", line: t("数据盘已用 {pct}%（{used} / {total}）", { pct: 72, used: "72 GB", total: "100 GB" }) + t("，按最近 7 天的速度约 {d} 天后写满", { d: 19 }), advice: t("先清回收区；不够就在 DigitalOcean 把数据盘再扩 50–100 GB（在线扩，约 15 分钟，每 100 GB 每月 +$10）。") },
      { key: "queue", level: "ok", line: t("导入排队：近 7 天 90% 的等待在 {p} 分钟以内，最长 {l} 分钟；现在 {w} 集在等", { p: 4.5, l: 12, w: 0 }), advice: "" },
      { key: "hours", level: "ok", line: t("本月已处理 {u} 小时音频，按现在的速度月底约 {p} 小时（这台服务器每月约 {b} 小时）", { u: 96, p: 124, b: 400 }), advice: "" },
      { key: "memory", level: "ok", line: t("内存最高用到 {p}%", { p: 61 }), advice: "" },
      { key: "people", level: "warn", line: t("账号 {n} 个，Cloudflare Access 免费名额 {s} 个", { n: 41, s: 50 }), advice: t("到 50 个以后每人每月 $7：在那之前把登录改成只用 LACUNA 自己的登录（关掉 Access），或者暂停发新邀请。") },
    ],
    activity: [
      { ts: t0 - 6 * 60, ev: "export.start", who: "chen.podcast@gmail.com", name: "chen", show: SHOWS[0], ep: "EP12" },
      { ts: t0 - 22 * 60, ev: "import.done", who: "huang.y@qq.com", name: "huang", show: SHOWS[1], ep: "EP7" },
      { ts: t0 - 50 * 60, ev: "feedback", who: "kimi.audio@icloud.com", name: "kimi", show: null, ep: null },
      { ts: t0 - 2 * H, ev: "user.signup", who: "yuki.s@gmail.com", name: "yuki", show: null, ep: null },
      { ts: t0 - 3 * H, ev: "poster.generate", who: "film.cast@outlook.com", name: "film", show: SHOWS[5], ep: "EP9" },
      { ts: t0 - 5 * H, ev: "import.error", who: "oak.radio@gmail.com", name: "oak", show: SHOWS[9], ep: "EP4" },
    ],
  };
}

function feedback(): FeedbackData {
  return {
    items: demoFeedback(),
    statuses: ["received", "working", "planned", "fixed", "shipped", "declined"],
    templates: [
      { id: "thanks", title: "谢谢，已记下", text: "谢谢你的反馈！我们已经记下了，有进展会在这里告诉你。" }, // i18n-ignore
      { id: "fixed", title: "已修好", text: "这个问题已经修好了，刷新一下页面就能用。谢谢你告诉我们！" }, // i18n-ignore
    ],
    known_tags: [
      "AI 剪错", // i18n-ignore
      "导入", // i18n-ignore
      "海报", // i18n-ignore
      "圆桌", // i18n-ignore
      "学到的规则", // i18n-ignore
    ],
  };
}

function prompts(): Prompts {
  const t0 = now();
  return {
    rate: { "5": 58, "4": 31, "3": 9, "2": 3, "1": 1 },
    saved: { none: 4, half: 18, "1-2h": 41, "2h+": 27, never: 12 },
    pmf: { very: 34, somewhat: 29, not: 11 },
    nps: { scores: { "10": 18, "9": 22, "8": 14, "7": 9, "6": 4, "5": 2, "3": 1 }, n: 70, score: 37, promoters: 40, passives: 23, detractors: 7 },
    quotes: [
      { kind: "rate", at: t0 - 4 * H, email: "chen.podcast@gmail.com", name: "chen", text: "停顿处理比我自己剪还自然。", stars: 5 }, // i18n-ignore
      { kind: "pmf", at: t0 - 30 * H, email: "two.cities@qq.com", name: "two", text: "已经离不开了，每周省两个小时。", choice: "very" }, // i18n-ignore
      { kind: "nps", at: t0 - 50 * H, email: "lisa.w@gmail.com", name: "lisa", text: "如果能自动发布就推荐给所有朋友。", score: 8 }, // i18n-ignore
    ],
    profiles: { n: 64, region: { na: 38, eu: 9, oceania: 7, asia: 6, cn: 4 }, editing: { self: 33, hired: 8, none: 12, new: 11 }, lang: { zh: 52, en: 12 } },
  };
}

function userDetail(email: string): UserDetail {
  const t0 = now();
  const u = demoUsers().find((x) => x.email === email) ?? demoUsers()[1];
  return {
    user: u,
    shows: [{ id: "s0", name: SHOWS[0], role: "admin", episodes: u.episodes, people: 2, updated: t0 - D }],
    activity: [
      { ts: t0 - 2 * H, ev: "export.start", ep: "EP12", show: SHOWS[0], props: {} },
      { ts: t0 - 3 * H, ev: "review.batch", ep: "EP12", show: SHOWS[0], props: {} },
      { ts: t0 - D, ev: "feedback", ep: null, show: null, props: {} },
      { ts: t0 - 4 * D, ev: "import.done", ep: "EP12", show: SHOWS[0], props: {} },
      { ts: u.created, ev: "user.signup", ep: null, show: null, props: {} },
    ],
    sessions: [
      { created: t0 - 3 * D, seen: t0 - 2 * H, device: "Chrome · macOS" },
      { created: t0 - 9 * D, seen: t0 - D, device: "Safari · iPhone" },
    ],
    devices: 2,
    notes: [{ id: "n1", target: `user:${u.email}`, ts: t0 - 5 * D, email: "leon@example.com", text: "小宇宙上认识的，做电影节目，很活跃。" }], // i18n-ignore
    hours: [{ id: "h1", email: u.email, created: t0 - 6 * D, status: "approved", hours: 2, reason: "", would_pay: true, granted: 2 }],
    feedback: demoFeedback().filter((f) => f.email === u.email),
    bonus_hours: 2,
  };
}

function access(): AccessData {
  const t0 = now();
  return {
    trials: [
      { id: "ar_d1", email: "anna.zhou@gmail.com", show: "东京漫步", note: "两个人在东京和温哥华远程录，想试试。", created: t0 - 5 * H, tracks: "separate", lang: "zh", status: "new" }, // i18n-ignore
      { id: "ar_d2", email: "mike.chan@outlook.com", show: "Weekend Brunch", note: "", created: t0 - 26 * H, tracks: "mixed", lang: "en", status: "new" },
      { id: "ar_d3", email: "xiaomei@qq.com", show: "灯下聊", note: "从小宇宙看到的。", created: t0 - 3 * D, tracks: "unsure", lang: "zh", status: "new" }, // i18n-ignore
      { id: "ar_d4", email: "dj.wang@gmail.com", show: "Echo Room", note: "Podcast about music production.", created: t0 - 4 * D, tracks: "separate", lang: "en", status: "new" },
    ],
    collabs: [{ id: "ar_d5", email: "pei.cohost@gmail.com", show: SHOWS[1], note: "", created: t0 - 8 * H, kind: "collab", by: "two.cities@qq.com", by_name: "two", status: "new" }],
    waitlist: [],
    invites: [
      { id: "inv1", email: "sydney.yu@gmail.com", role: "member", by: "leon@example.com", plan: "basic", created: t0 - 2 * D, exp: t0 + 5 * D, space: "new", source: "xiaoyuzhou" },
      { id: "inv2", email: "berlin.zh@gmail.com", role: "member", by: "leon@example.com", plan: "basic", created: t0 - 5 * D, exp: t0 + 2 * D, space: "new", source: "friend" },
    ],
    seats: { used: 17, total: 20 },
    approval: true,
    sources: [
      { source: "xiaoyuzhou", invited: 11, joined: 9, week4: 6 },
      { source: "friend", invited: 8, joined: 8, week4: 6 },
      { source: "survey", invited: 5, joined: 3, week4: 1 },
      { source: "request", invited: 4, joined: 3, week4: 1 },
    ],
    source_ids: ["xiaoyuzhou", "friend", "survey", "request", "pei", "other"],
  };
}

function hours(): HoursData {
  const t0 = now();
  const us = demoUsers();
  return {
    requests: [
      { id: "hr_d1", email: us[2].email, name: us[2].name, plan: "basic", created: t0 - 3 * H, status: "new", hours: 2, reason: "这个月录了两期特别节目，每期两个多小时。", would_pay: true }, // i18n-ignore
      { id: "hr_d2", email: us[5].email, name: us[5].name, plan: "basic", created: t0 - 20 * H, status: "new", hours: 4, reason: "We do a weekly 90-minute show.", would_pay: false },
      { id: "hr_d3", email: us[8].email, name: us[8].name, plan: "basic", created: t0 - 2 * D, status: "new", hours: 1, reason: "", would_pay: true },
    ],
    decided: [{ id: "hr_d0", email: us[3].email, name: us[3].name, created: t0 - 9 * D, status: "approved", hours: 2, granted: 2, reason: "", would_pay: false, decided_at: t0 - 8 * D }],
    usage: us.filter((u) => u.role === "member").map((u) => ({ email: u.email, name: u.name, plan: u.plan, hours: u.hours, used: u.hours_used })),
    plans: [
      { id: "trial", name: "", hours: 1, hours_once: true, shows: 1, collaborators: 0 },
      { id: "basic", name: "", hours: 4, hours_once: false, shows: 1, collaborators: 2 },
      { id: "pro", name: "", hours: 12, hours_once: false, shows: 5, collaborators: null },
    ],
    beta_end: null,
    quota: { enforce: true, must_fit: false, staff_exempt: true, repeat_free: true },
    month_hours: 31.5,
    willing: [
      { email: us[2].email, name: us[2].name, at: t0 - 3 * H, reason: "这个月录了两期特别节目，每期两个多小时。", where: "hours" }, // i18n-ignore
      { email: us[8].email, name: us[8].name, at: t0 - 2 * D, reason: "", where: "hours" },
    ],
  };
}

function shows(): ShowsData {
  const t0 = now();
  seed = 11;
  return {
    shows: SHOWS.map((name, i) => ({
      id: `s${i}`,
      name,
      creator: demoUsers()[i + 1]?.email ?? null,
      members: 1 + (i % 3),
      episodes: 2 + ((i * 5) % 14),
      created: t0 - (40 - i * 3) * D,
      last: t0 - (i % 6) * D - 3 * H,
      size: Math.floor((0.4 + ((i * 7) % 30) / 10) * 1e9),
      archived: false,
      sample: false,
      support: null,
      language: i === 4 || i === 5 || i === 9 ? "en" : "zh",
    })),
    stuck: [
      { sid: "s9", show: SHOWS[9], ep: "EP4", last: t0 - 5 * H, who: "oak.radio@gmail.com", ev: "import.error", why: "failed" },
      { sid: "s3", show: SHOWS[3], ep: "EP6", last: t0 - 17 * D, who: "sunset.pod@gmail.com", ev: "import.done", why: "idle" },
    ],
    votes: { apple: 21, spotify: 17, youtube: 9, amazon: 3 },
    voters: 26,
    sizes_at: t0 - 12 * 60,
  };
}

function trash(): TrashData {
  const t0 = now();
  return {
    items: [
      { kind: "show", id: "s_old-1", name: "周末不加班", by: "tofu.talks@gmail.com", deleted_at: t0 - 8 * D, left_days: 52, size: 2.1e9 }, // i18n-ignore
      { kind: "user", id: "ridge.fm@gmail.com", name: "ridge.fm@gmail.com", by: "ridge.fm@gmail.com", deleted_at: t0 - 53 * D, left_days: 7, size: null },
    ],
    keep_days: 60,
  };
}

function ai(): AiData {
  const o = overview();
  return {
    ...o.ai,
    month: new Date().toISOString().slice(0, 7),
    per_hour: 2.41,
    target: 1.8,
    hours: 75.7,
    features: { first_cut: 121.3, chat: 28.4, notes: 14.9, poster: 11.2, rules: 6.6 },
    top: demoUsers()
      .slice(0, 10)
      .map((u) => ({ email: u.email, name: u.name, cost: u.ai, hours: +(u.ai / 2.4).toFixed(1), per_hour: 2.4 })),
    fails: { imports: 3, refusals: 1 },
    accuracy: [
      { category: "pause", kept: 0.91, n: 1840 },
      { category: "filler", kept: 0.84, n: 1210 },
      { category: "interjection", kept: 0.77, n: 402 },
      { category: "crosstalk", kept: 0.66, n: 233 },
      { category: "content", kept: 0.58, n: 96 },
    ],
    rules_month: 214,
    calls: 1912,
  };
}

function growth(weeks: number): GrowthData {
  const w = (a: number[]) => a.slice(-weeks).concat([]).slice(0, weeks);
  const base = [22, 25, 31, 34, 38, 44, 49, 52, 55, 61, 66, 72, 78, 84, 88, 91, 97];
  const sign = [3, 2, 5, 4, 6, 8, 7, 9, 10, 11, 9, 14, 12, 18, 15, 13, 16];
  const t0 = now();
  return {
    wau: w(base),
    signups: w(sign),
    activation: { rate: 0.71, of: 121, n: 86 },
    per_user_month: 3.4,
    active_month: 118,
    langs: { zh: 151, en: 35 },
    funnel: [
      { step: "import.start", n: 612 },
      { step: "import.done", n: 588 },
      { step: "review", n: 541 },
      { step: "export.start", n: 497 },
      { step: "publish.generate", n: 303 },
    ],
    durations: [
      { from: "import.start", to: "import.done", median: 14 * 60, n: 588 },
      { from: "import.done", to: "review", median: 3.2 * H, n: 541 },
      { from: "review", to: "export.start", median: 46 * 60, n: 497 },
      { from: "export.start", to: "publish.generate", median: 9 * 60, n: 303 },
    ],
    features: [
      { feature: "chat", pct: 0.62 },
      { feature: "notes", pct: 0.58 },
      { feature: "poster", pct: 0.44 },
      { feature: "rules", pct: 0.39 },
      { feature: "music", pct: 0.31 },
      { feature: "levels", pct: 0.27 },
      { feature: "coedit", pct: 0.22 },
    ],
    cohorts: [
      [1, 0.82, 0.71, 0.66, 0.61, 0.58],
      [1, 0.79, 0.7, 0.63, 0.6],
      [1, 0.84, 0.74, 0.69],
      [1, 0.77, 0.66],
      [1, 0.81],
      [1],
    ].map((weeksRow, i) => ({ start: t0 - (6 - i) * 7 * D, size: 14 + i * 2, weeks: weeksRow })),
    regions: { na: 38, eu: 9, oceania: 7, asia: 6, cn: 4 },
  };
}

function system(): SystemData {
  const t0 = now();
  seed = 3;
  return {
    disk: { used: 36e9, total: 50e9, pct: 0.72 },
    parts: { raw: 21e9, episodes: 6.2e9, exports: 3.1e9, trash: 4.1e9, music: 0.6e9, other: 1e9 },
    sizes_at: t0 - 12 * 60,
    backup: { at: t0 - 7 * H, snapshot: t0 - 7 * H },
    running: [
      { sid: "s0", show: SHOWS[0], kind: "import", episode: "EP13", state: "running", progress: 0.42, started: t0 - 9 * 60 },
      { sid: "s5", show: SHOWS[5], kind: "export", episode: "EP10", state: "running", progress: null, started: null },
    ],
    samples: Array.from({ length: 48 }, (_, i) => ({ ts: t0 - (47 - i) * 300, cpu: Math.round((18 + R() * 30 + (i > 38 ? 25 : 0)) * 10) / 10, mem: Math.round((52 + R() * 10) * 10) / 10 })),
    errors: [{ method: "POST", path: "/api/imports", status: 504, n: 2, last: t0 - 5 * H }],
    started: t0 - 2 * D - 4 * H,
    version: "a1b2c3d4e5",
    alerts: overview().alerts,
    cpus: 4,
    storage: { retention: { raw_tracks: false, old_exports: true }, cold: { on: true, moving: true, bytes: 41e9, after_days: 14 } },
    ai: { first_cut_batch: false },
  };
}

function settings(): SettingsData {
  const t0 = now();
  return {
    notice: {
      on: false,
      zh: "今晚 10 点维护 5 分钟，正在进行的导入不受影响。", // i18n-ignore
      en: "Maintenance tonight at 10 pm for 5 minutes. Running imports are not affected.",
      until: null,
    },
    maintenance: { on: false },
    staff: [
      { email: "leon@example.com", name: "Leon", role: "owner", twofa: true, last_admin: t0 - 40 * 60 },
      { email: "lisa.w@gmail.com", name: "lisa", role: "admin", twofa: true, last_admin: null },
    ],
    sessions: [
      { id: "a1", email: "leon@example.com", created: t0 - 40 * 60, exp: t0 + 7 * H, agent: "Chrome · Windows", country: "Canada", current: true },
      { id: "a2", email: "leon@example.com", created: t0 - 5 * H, exp: t0 + 3 * H, agent: "Safari · iPhone", country: "Canada", current: false },
    ],
    terms: [
      "LACUNA",
      "洛城二三事", // i18n-ignore
      "Pei",
      "Show notes",
      "小宇宙", // i18n-ignore
      "Spotify",
      "Apple Podcasts",
    ],
    mail: { configured: true, source: "env", sender: "LACUNA <noreply@lacunastudio.app>" },
    key: { present: true, source: "env" },
    turnstile: false,
    access: true,
    cloud: true,
    digest: { hour: 8, tz: "America/Vancouver", last: new Date().toISOString().slice(0, 10) },
    budget: 300,
  };
}

function audit(): { rows: AuditRow[] } {
  const t0 = now();
  const rows: [number, string, string, Record<string, unknown>][] = [
    [40 * 60, "admin.login", "leon@example.com", {}],
    [2 * H, "hours.approve", "kimi.audio@icloud.com", { hours: 2 }],
    [3 * H, "feedback.reply", "fb_demo1", { status: "shipped", adopted: true }],
    [26 * H, "invite.send", "sydney.yu@gmail.com", { role: "member", source: "xiaoyuzhou" }],
    [2 * D, "trash.restore.show", "s_old-2", {}],
    [3 * D, "user.update", "lisa.w@gmail.com", { plan: "pro" }],
    [5 * D, "site.notice", "", { on: true }],
  ];
  return { rows: rows.map(([ago, action, target, data], i) => ({ id: 100 - i, ts: t0 - ago, email: "leon@example.com", action, target, data })) };
}

function notes(target: string): { notes: Note[] } {
  return target === "fb:fb_demo0"
    ? { notes: [{ id: "n0", target, ts: now() - 2 * H, email: "leon@example.com", text: "确实是个问题：给审阅加一个「这里别剪」的标记？" }] } // i18n-ignore
    : { notes: [] };
}

/** The demo answer for a GET of the admin API. */
export function demoData(url: string): unknown {
  const u = new URL(url, "http://demo");
  const p = u.pathname.replace(/^\/api\/admin/, "");
  if (p === "/auth/me") return ME;
  if (p === "/overview") return overview();
  if (p === "/feedback") return feedback();
  if (p === "/feedback/prompts") return prompts();
  if (p === "/notes") return notes(u.searchParams.get("target") || "");
  if (p === "/users") return { users: demoUsers(), plans: hours().plans };
  if (p.startsWith("/users/")) return userDetail(decodeURIComponent(p.slice(7)));
  if (p === "/access") return access();
  if (p === "/hours") return hours();
  if (p === "/shows") return shows();
  if (p === "/trash") return trash();
  if (p === "/ai") return ai();
  if (p === "/growth") return growth(Number(u.searchParams.get("weeks")) || 8);
  if (p === "/system") return system();
  if (p === "/settings") return settings();
  if (p === "/audit") return audit();
  return null;
}
