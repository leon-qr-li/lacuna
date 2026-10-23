// The bubble tour of LACUNA 示例节目 (new-user batch, tour v3): a locked demo (Leon 2026-10-23, 16 steps).
// Read first, then act, never both at once: a step's bubble says what LACUNA is about to do; only after 知道了
// does LACUNA do it (`act`, the clicked control flashing), then the tour goes on by itself, or shows `result`
// first. A chapter's last step ends with LACUNA clicking 下一步 (Tour.tsx).
import { selectOnTimeline, showOnTimeline } from "../manual/EditLanes";
import type { Episode } from "../../api";
import type { Player } from "../../usePlayer";
import { t } from "../../i18n";

/** Where the tour's spots are on the current cut (GET …/tour/marks), seconds. */
export interface Marks {
  hosts: [string, string];
  actor: [number, number] | null;
  water: [number, number] | null;
  cough: [number, number] | null;
}

export interface Ctx {
  ep: Episode;
  id: string;
  mode: string;
  marks: Marks | null;
  player: Player;
  /** what a step noted while LACUNA did it */
  memo: Record<string, unknown>;
  /** still on this step (an `enter` that waits checks this before each next action) */
  alive: () => boolean;
}

type Target = string | ((c: Ctx) => Element[]);

export interface Step {
  id: string; // kept on the server as the place to come back to: a-z0-9, up to 12
  ch: number; // chapter 1-9
  mode: string; // the page it is on
  title: (h: Hosts) => string;
  body: (h: Hosts, c?: Ctx) => string; // **bold**
  /** lit up (their union); nothing found → the bubble sits in the middle */
  target?: Target[];
  /** sets the scene before the bubble shows (seek, scroll, open a panel): never something the person should watch */
  enter?: (c: Ctx) => void;
  /** what LACUNA does once the person has read the bubble and pressed 知道了 */
  act?: (c: Ctx) => Promise<unknown>;
  /** after `act`: wait for this (at most 20 s) */
  done?: (c: Ctx) => boolean;
  /** shown while LACUNA acts */
  hint?: (h: Hosts) => string;
  /** shown after `act`, with 知道了 again (the outcome is on screen and worth a sentence) */
  result?: (h: Hosts) => string;
  side?: "top" | "bottom" | "left" | "right";
  /** the bubble keeps clear of these too (default: only the lit part) */
  around?: string[];
  /** a dashed box on the timeline: the spot the step is about (track null = all tracks) */
  box?: (c: Ctx) => { track: string | null; a: number; b: number } | null;
}

export type Hosts = Record<string, string> & {
  a: string;
  b: string;
};

export const CHAPTERS = 8;
export const chapterName = (n: number) =>
  [t("先听原始录音"), t("审阅改动"), t("对 LACUNA 说"), t("手动剪辑"), t("声音"), t("配乐"), t("导出"), t("发布")][n - 1] ?? "";

const q = (sel: string) => document.querySelector(sel);
const click = (sel: string) => (q(sel) as HTMLElement | null)?.click();
export const wait = (ms: number) => new Promise((r) => window.setTimeout(r, ms));
/** waits until f() is true, at most ms */
export const until = async (f: () => unknown, ms = 10_000) => {
  const end = Date.now() + ms;
  while (!f() && Date.now() < end) await wait(100);
  return !!f();
};
/** LACUNA clicks something the way a person would be seen to: it flashes, then the click */
export const tap = async (el: Element | string | null | undefined, ms = 650) => {
  const e = (typeof el === "string" ? q(el) : el) as HTMLElement | null;
  if (!e) return;
  e.classList.add("tour-tap");
  await wait(ms - 250);
  e.classList.add("tour-press"); // the press itself, just before the click
  await wait(250);
  e.classList.remove("tour-tap", "tour-press");
  e.click();
};
/** Type into a React-controlled textarea / input */
export function fill(sel: string, text: string) {
  const el = q(sel) as HTMLTextAreaElement | HTMLInputElement | null;
  if (!el) return;
  const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value")?.set?.call(el, text);
  el.dispatchEvent(new Event("input", { bubbles: true }));
}
/** types it in, a few characters at a time, so it can be watched */
const type = async (c: Ctx, sel: string, text: string) => {
  const chars = [...text];
  const n = Math.max(1, Math.ceil(chars.length / 14));
  for (let i = n; i < chars.length + n && c.alive(); i += n) {
    fill(sel, chars.slice(0, i).join(""));
    await wait(55);
  }
};
const manual = (ep: Episode, lift: boolean) => ep.edits.filter((e) => e.source === "manual" && !!e.tracks === lift).length;
const playing = () => [...document.querySelectorAll("audio")].some((a) => !a.paused);
/** LACUNA clicks a play button and waits until it has played (at most ms) */
const hear = async (c: Ctx, sel: string, ms = 12_000) => {
  if (!c.alive()) return;
  await tap(sel);
  await until(playing, 2000);
  await until(() => !playing() || !c.alive(), ms);
};
const intro = '[data-testid="placement"][data-role="intro"]';
const select = (span: [number, number] | null | undefined, pad = 0) => span && selectOnTimeline(span[0] - pad, span[1] + pad);

export const TOUR_CHAT = () => t("把阿乔问演员名字的那两句删掉");
export const TOUR_MUSIC = () => t("说话时片头音乐再小一点");

export const STEPS: Step[] = [
  // 1 the raw recording: a dialog of its own (Tour.tsx)
  { id: "raw", ch: 1, mode: "review", title: () => t("先听听没剪过的样子"), body: () => t("这是示例节目开头 30 秒的原始录音：有重说、口头禅、冷场，两人一个大声一个小声。教程最后会放剪好的同一段给你对比。") },

  // 2 审阅改动
  { id: "rlist", ch: 2, mode: "review", side: "right", target: [".review-nav"],
    title: () => t("LACUNA 拿不准的 3 处"),
    body: () => t("LACUNA 已经剪完了第一版。大部分改动它有把握，左边只列出它拿不准的 **3 处**，等你过目。停顿、口头禅这些小改动，整集试听时都能听到。") },
  { id: "rab", ch: 2, mode: "review", side: "bottom", target: [".rv-act .ab-seg"],
    act: async (c) => {
      await hear(c, ".rv-act .ab-opt:nth-of-type(1)");
      await wait(400);
      await hear(c, ".rv-act .ab-opt:nth-of-type(2)");
    },
    title: () => t("先听，再决定"),
    body: (h) => t("第 1 处：{a}开头把一句话重说了一遍。按 **知道了**，LACUNA 先放 **A · 原话**（删之前），再放 **B · 剪后**（删之后）。", h),
    hint: () => t("正在播放…") },
  { id: "rdecide", ch: 2, mode: "review", side: "top", target: [".review-main"],
    act: async (c) => {
      for (let i = 0; i < 3 && c.alive(); i++) {
        await until(() => q(".rv-act button.btn-primary"));
        await tap(".rv-act button.btn-primary");
        await wait(900);
      }
    },
    done: (c) => (c.ep.pending_review ?? 0) === 0,
    title: () => t("保留，还是恢复？"),
    body: () => t("删得对就点 **保留**（键盘 K），想留原话就点 **恢复原话**（R）。删除早已生效，你只是确认。这 3 处都删对了：按 **知道了**，LACUNA 一处处点 **保留**。"),
    hint: () => t("正在确认 3 处…") },

  // 3 对 LACUNA 说
  { id: "csend", ch: 3, mode: "listen", side: "left", target: ["form.chat-form"],
    enter: (c) => {
      click('[data-testid="tab-ai"]');
      if (c.marks?.actor) { c.player.seek(c.marks.actor[0]); showOnTimeline(c.marks.actor[0] - 1, c.marks.actor[1] + 1); }
    },
    box: (c) => (c.marks?.actor ? { track: c.marks.hosts[1], a: c.marks.actor[0], b: c.marks.actor[1] } : null),
    act: async (c) => {
      await type(c, "form.chat-form textarea", TOUR_CHAT());
      await wait(500);
      await tap("form.chat-form button.btn-primary");
    },
    done: (c) => c.ep.proposals.length > 0,
    title: () => t("直接跟 LACUNA 说"),
    body: (h) => t("虚线框里，{b}想不起演员名字，来回两句，中间还冷场了。这种地方直接跟 LACUNA 说就能剪。按 **知道了**，LACUNA 替你写一句「{text}」并发送。", { ...h, text: TOUR_CHAT() }),
    hint: () => t("LACUNA 正在回答…") },
  { id: "cab", ch: 3, mode: "listen", side: "left", target: ['[data-testid="proposal"]'],
    act: async (c) => {
      await tap('[data-testid="proposal"] .btn-outline-accent');
      await until(() => q('[data-testid="proposal"] .ab button'));
      await hear(c, '[data-testid="proposal"] .ab button:nth-of-type(1)');
      await wait(400);
      await hear(c, '[data-testid="proposal"] .ab button:nth-of-type(2)');
    },
    title: () => t("批准前，可以先听"),
    body: () => t("LACUNA 不会直接改。批准前，你可以先听一下：**▶ 现在** 是原样，**▶ 改后** 是删掉这两句以后。按 **知道了**，LACUNA 替你各放一遍。"),
    hint: () => t("正在播放…") },
  { id: "cok", ch: 3, mode: "listen", side: "left", target: ['[data-testid="proposal"]'],
    act: () => tap('[data-testid="proposal"] .btn-primary'),
    done: () => !q('[data-testid="proposal"]') && !!q(".pstate.ok"),
    title: () => t("满意就批准"),
    body: () => t("满意就点 **批准**；不满意，平时可以点「再改」接着说。按 **知道了**，LACUNA 替你批准。"),
    hint: () => t("正在批准…") },

  // 4 手动剪辑
  { id: "dcut", ch: 4, mode: "listen", side: "bottom", target: [".ml .ml-body"],
    enter: (c) => {
      const w = c.marks?.water;
      if (w) { c.player.seek(Math.max(0, w[0] - 3)); showOnTimeline(w[0] - 2, w[1] + 2); }
    },
    box: (c) => (c.marks?.water ? { track: c.marks.hosts[0], a: c.marks.water[0], b: c.marks.water[1] } : null),
    act: async (c) => {
      c.memo.n = manual(c.ep, false);
      select(c.marks?.water);
      await until(() => q('[data-testid="ml-cut"]'), 3000);
      await wait(900);
      await tap('[data-testid="ml-cut"]');
    },
    done: (c) => manual(c.ep, false) > Number(c.memo.n ?? 0),
    title: () => t("自己动手删一段"),
    body: (h) => t("这是剪辑时间线：每人一条轨道，**橙色竖线** 是剪切点。{a}说「等一下，我喝口水」（虚线框），这句不要。平时在轨道上 **按住鼠标** 从左拖到右选中它，再点菜单里的 **删掉这段**。按 **知道了**，LACUNA 替你做一遍。", h),
    hint: () => t("正在删…") },
  { id: "dmute", ch: 4, mode: "listen", side: "bottom", target: [".ml .ml-body"],
    enter: (c) => {
      const k = c.marks?.cough;
      if (k) { c.player.seek(Math.max(0, k[0] - 3)); showOnTimeline(k[0] - 2, k[1] + 2); }
    },
    box: (c) => (c.marks?.cough ? { track: c.marks.hosts[0], a: c.marks.cough[0] - 0.1, b: c.marks.cough[1] + 0.1 } : null),
    act: async (c) => {
      c.memo.n = manual(c.ep, true);
      select(c.marks?.cough, 0.05);
      const sel = `[data-testid="ml-mute-${c.marks?.hosts[0] ?? ""}"]`;
      await until(() => q(sel), 3000);
      await wait(900);
      await tap(sel);
    },
    done: (c) => manual(c.ep, true) > Number(c.memo.n ?? 0),
    title: (h) => t("{b}说话时，{a}咳了一声", h),
    body: (h) => t("删掉整段会把{b}的话也删了。平时选中咳嗽那一小段（虚线框），点 **只静音 {a}**：{b}的话留着，只有{a}那条轨道变安静。按 **知道了**，LACUNA 替你做一遍。", h),
    hint: () => t("正在静音…") },

  // 5 声音
  { id: "vauto", ch: 5, mode: "levels", side: "bottom", target: [".levels-card"],
    act: (c) => tap('[data-tour="levels-auto"]').then(() => until(() => !q('[data-tour="levels-auto"][disabled]') || !c.alive())),
    title: () => t("一个大声，一个小声"),
    body: (h) => t("{a}离麦克风近，比{b}响很多。尺子上白线是原始音量，彩色条是现在，绿线是目标。按 **知道了**，LACUNA 替你点 **统一两人音量**，两人都到绿线。", h),
    hint: () => t("正在统一音量…") },

  // 6 配乐
  { id: "uput", ch: 6, mode: "music", side: "right", target: ['[data-tour="music-library"]'],
    act: async (c) => {
      for (const [kind, i, role] of [["intro", 1, "intro"], ["outro", 2, "outro"]] as const) {
        if (!c.alive() || q(`[data-testid="placement"][data-role="${role}"]`)) continue;
        await tap(`[data-tour="music-asset-${kind}"] .mlib-put`);
        await wait(500);
        await tap(`[data-tour="music-asset-${kind}"] .mlib-menu [role="menuitem"]:nth-of-type(${i})`);
        await until(() => q(`[data-testid="placement"][data-role="${role}"]`), 8000);
        await wait(500);
      }
    },
    done: () => !!q(intro) && !!q('[data-testid="placement"][data-role="outro"]'),
    title: () => t("放上片头和片尾"),
    body: () => t("左边是素材库，示例准备了 3 首 CC0 授权的音乐。按 **知道了**，LACUNA 把第一首放成 **片头**、第二首放成 **片尾**：有人开口时音乐会自动压低。"),
    hint: () => t("正在放音乐…") },
  { id: "usend", ch: 6, mode: "music", side: "top", target: ['[data-tour="music-assist"]'],
    act: async (c) => {
      await type(c, '[data-tour="music-assist"] textarea', TOUR_MUSIC());
      await wait(500);
      await tap('[data-tour="music-assist"] .btn-primary');
      await until(() => q('[data-testid="music-draft"]'), 15_000);
      await wait(1500);
      await tap('[data-testid="music-draft"] .btn-primary');
    },
    done: () => !q('[data-testid="music-draft"]'),
    title: () => t("说一句，让 LACUNA 调"),
    body: () => t("不想自己调数值，直接说就行。LACUNA 的改动先变成建议，满意再 **采用**。按 **知道了**，LACUNA 替你发一句「{text}」，再点采用。", { text: TOUR_MUSIC() }),
    hint: () => t("LACUNA 正在调…") },

  // 7 导出
  { id: "xstart", ch: 7, mode: "export", side: "bottom", target: ['[data-tour="export-formats"]', '[data-tour="export-start"]', ".xmain .job"],
    act: () => tap('[data-tour="export-start"]'),
    done: () => !!q('[data-testid="export-result"]'),
    title: () => t("导出"),
    body: () => t("**MP3** 体积小，适合分享；**WAV** 音质最好。按 **知道了**，LACUNA 替你点 **开始导出**：整集重新合成，再统一响度。要多久看节目长短，长的节目要等几分钟。"),
    hint: () => t("正在导出…") },
  { id: "xsum", ch: 7, mode: "export", side: "left", target: ['[data-tour="export-summary"]', '[data-tour="export-standard"]'],
    title: () => t("这一集的结果"),
    body: () => t("原始多长、成品多长、剪掉多少、配乐几处，都在这里。响度统一到 −16 LUFS，真峰值不超过 −1 dBTP，符合 Apple Podcasts、Spotify 等平台的标准，可以直接上传。") },

  // 8 发布
  { id: "ptext", ch: 8, mode: "publish", side: "bottom", target: ['[data-tour="publish-title-card"]', '[data-tour="publish-generate"]'],
    act: async () => {
      if (!q('[data-testid="publish-title"]')) await tap('[data-tour="publish-generate"]');
    },
    done: () => !!q('[data-testid="publish-title"]') && !!q('[data-testid="show-notes"]'),
    title: () => t("发布资料"),
    body: () => t("按 **知道了**，LACUNA 读剪好的文字稿，写这一集的标题、一句话简介和带时间戳的 show notes。"),
    hint: () => t("LACUNA 正在写…"),
    result: () => t("写好了：标题、备选标题、简介和 show notes，点一下就能复制，和导出的音频一起贴到播客平台。剪辑再改，时间戳一键更新。") },
  { id: "pposter", ch: 8, mode: "poster", side: "bottom", target: ['[data-testid="poster-card"]', '[data-tour="poster-generate"]'],
    act: async () => {
      if (!q('[data-testid="poster-card"]')) await tap('[data-tour="poster-generate"]');
    },
    done: () => !!q('[data-testid="poster-card"]'),
    title: () => t("海报"),
    body: () => t("按 **知道了**，LACUNA 按标题和简介画几版方形封面。"),
    hint: () => t("LACUNA 正在画…"),
    result: () => t("挑一张就能用；不满意，说一句话让它改。示例就到这里，最后听一下剪前剪后的对比。") },
];

export const DONE = "done";
