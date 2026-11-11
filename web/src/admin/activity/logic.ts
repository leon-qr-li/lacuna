// 用户动态 (decision 2026-10-31-admin-user-activity): the account's events, newest first, cut into days and
// sessions (a gap of more than 30 minutes starts a new one) and merged repeats ("手动剪辑 ×14"). Done here, not on
// the server, so days follow the viewer's own clock.
import { t, locale } from "../i18n";
import { eventName } from "../labels";

export interface ActRow {
  ts: number;
  ev: string;
  sid?: string | null;
  show: string | null;
  ep: string | null;
  title?: string | null;
  props: Record<string, unknown>;
}

export interface ActWindow {
  user: { email: string; name: string | null; role: string; plan: string };
  rows: ActRow[];
  start: number;
  end: number;
  older: boolean;
}

export type Kind = "edit" | "ai" | "io" | "account";
export type Filter = "all" | Kind | "failed";

export interface Item {
  ev: string; // without ".failed"
  failed: boolean;
  rows: ActRow[]; // newest first
  ts: number;
  ep: string | null;
  title: string | null;
  show: string | null;
}

export interface Session {
  start: number;
  end: number;
  items: Item[];
  n: number;
  shows: string[];
}

export interface Day {
  key: string;
  label: string;
  sessions: Session[];
}

export const GAP_S = 30 * 60;

const KIND: Record<string, Kind> = {
  edit: "edit",
  fillers: "edit",
  levels: "edit",
  music: "edit",
  rule: "edit",
  transcript: "edit",
  chat: "ai",
  review: "ai",
  poster: "ai",
  lessons: "ai",
  dictation: "ai",
  import: "io",
  export: "io",
  publish: "io",
  library: "io",
  episode: "io",
};
// AI work whose first word says otherwise
const AI_EVENTS = new Set(["music.auto", "music.chat", "levels.auto", "publish.generate"]);

export const base = (ev: string) => ev.replace(/\.failed$/, "");
export const isFailed = (ev: string) => ev.endsWith(".failed") || ["import.error", "import.interrupted", "export.error"].includes(ev);

export function kindOf(ev: string): Kind {
  const b = base(ev);
  if (AI_EVENTS.has(b)) return "ai";
  return KIND[b.split(".")[0]] ?? "account";
}

export function tone(it: Item): "bad" | "ok" | "ai" | "" {
  if (it.failed || isFailed(it.ev)) return "bad";
  if (it.ev === "import.done" || it.ev === "export.done") return "ok";
  return kindOf(it.ev) === "ai" ? "ai" : "";
}

export function keep(f: Filter, ev: string): boolean {
  return f === "all" || (f === "failed" ? isFailed(ev) : kindOf(ev) === f);
}

/** Rows (newest first) into sessions, each with its repeats merged. */
export function sessions(rows: ActRow[], gap = GAP_S): Session[] {
  const out: Session[] = [];
  let cur: ActRow[] = [];
  const flush = () => {
    if (!cur.length) return;
    const items = merge(cur);
    const shows = [...new Set(cur.map((r) => r.show).filter((s): s is string => !!s))];
    out.push({ start: cur[cur.length - 1].ts, end: cur[0].ts, items, n: cur.length, shows });
    cur = [];
  };
  for (const r of rows) {
    if (cur.length && cur[cur.length - 1].ts - r.ts > gap) flush();
    cur.push(r);
  }
  flush();
  return out;
}

/** Next to each other, the same thing on the same episode: one line. */
export function merge(rows: ActRow[]): Item[] {
  const out: Item[] = [];
  for (const r of rows) {
    const last = out[out.length - 1];
    const failed = r.ev.endsWith(".failed");
    if (last && last.ev === base(r.ev) && last.failed === failed && last.ep === r.ep) {
      last.rows.push(r);
      continue;
    }
    out.push({ ev: base(r.ev), failed, rows: [r], ts: r.ts, ep: r.ep, title: r.title ?? null, show: r.show });
  }
  return out;
}

const dayKey = (ts: number) => {
  const d = new Date(ts * 1000);
  return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
};

export function dayLabel(ts: number, now = Date.now() / 1000): string {
  const d = new Date(ts * 1000).toLocaleDateString(locale, { month: "short", day: "numeric", weekday: "short" });
  if (dayKey(ts) === dayKey(now)) return t("今天 · {d}", { d });
  if (dayKey(ts) === dayKey(now - 86400)) return t("昨天 · {d}", { d });
  return d;
}

export function days(list: Session[], now = Date.now() / 1000): Day[] {
  const out: Day[] = [];
  for (const s of list) {
    const key = dayKey(s.end);
    const last = out[out.length - 1];
    if (last && last.key === key) last.sessions.push(s);
    else out.push({ key, label: dayLabel(s.end, now), sessions: [s] });
  }
  return out;
}

const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : 0);
const sum = (rows: ActRow[], k: string) => rows.reduce((a, r) => a + num(r.props[k]), 0);
const mins = (s: number) => Math.max(1, Math.round(s / 60));
const one = (n: number) => Math.round(n * 10) / 10;

const STEP: Record<string, () => string> = {
  models: () => t("准备识别模型"),
  features: () => t("分析停顿、语速和重叠"),
  first_cut: () => t("初剪"),
  episode: () => t("生成审阅"),
  names: () => t("核对专有名词"),
};
export const stepName = (s: string) => (s.startsWith("asr_") ? t("识别分轨") : STEP[s]?.() ?? s);

const STATUS: Record<number, () => string> = {
  409: () => t("和别的改动冲突"),
  413: () => t("文件太大"),
  422: () => t("内容不对，被拒绝"),
  429: () => t("次数或额度用完了"),
};
export function statusText(code: number): string {
  if (code >= 500) return t("服务器出错（{code}）", { code });
  return STATUS[code]?.() ?? t("没成功（{code}）", { code });
}

/** The numbers worth a line under the event, in words. */
export function detail(it: Item): string {
  const rs = it.rows;
  const p = rs[0].props;
  if (it.failed) return statusText(num(p.status));
  switch (it.ev) {
    case "edit.manual": {
      const s = sum(rs, "seconds");
      return s ? t("共删 {s} 秒", { s: one(s) }) : "";
    }
    case "edit.fillers": {
      const n = sum(rs, "n");
      return n ? t("去掉 {n} 处口头禅", { n }) : "";
    }
    case "review.decide": {
      const k = rs.filter((r) => r.props.action === "keep" || r.props.action === "apply").length;
      const r = rs.filter((x) => x.props.action === "restore").length;
      return t("保留 {k} · 恢复 {r}", { k, r });
    }
    case "review.batch": {
      const n = sum(rs, "edits");
      return n ? t("{n} 处", { n }) : "";
    }
    case "import.done":
      return p.audio_s ? t("音频 {m} 分钟", { m: mins(num(p.audio_s)) }) : "";
    case "import.error":
    case "import.interrupted":
      return typeof p.failed_step === "string" ? t("停在「{step}」", { step: stepName(p.failed_step) }) : "";
    case "export.done":
      return p.length_s ? t("成品 {m} 分钟 · 用时 {s} 秒", { m: mins(num(p.length_s)), s: Math.round(num(p.seconds)) }) : "";
    case "export.error":
      return p.seconds ? t("用时 {s} 秒", { s: Math.round(num(p.seconds)) }) : "";
    case "user.signup":
      return p.invited ? t("通过邀请") : "";
    default:
      return "";
  }
}

/** The event in words, starting with a capital in English (the labels are written to follow a name). */
export function what(ev: string): string {
  const s = eventName(base(ev));
  return s ? s[0].toUpperCase() + s.slice(1) : s;
}

export function clock(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
}

/** How many of the rows fall on each of the last 7 days (oldest first), for the drawer's little bars. */
export function week(rows: ActRow[], now = Date.now() / 1000): { label: string; n: number }[] {
  const out: { label: string; n: number }[] = [];
  for (let i = 6; i >= 0; i--) {
    const ts = now - i * 86400;
    const key = dayKey(ts);
    out.push({ label: new Date(ts * 1000).toLocaleDateString(locale, { weekday: "narrow" }), n: rows.filter((r) => dayKey(r.ts) === key).length });
  }
  return out;
}
