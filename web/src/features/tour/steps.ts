// The bubble tour of LACUNA 示例节目 (new-user batch, tour v3): a locked demo (Leon 2026-10-23, 15 steps in 7 chapters, as in the prototype).
// Read first, then act, never both at once: a step's bubble says what LACUNA is about to do; only after 知道了
// does LACUNA do it (`act`, the clicked control flashing), then the tour goes on by itself, or shows `result`
// first. A chapter's last step ends with LACUNA clicking 下一步 (Tour.tsx).
import { selectOnTimeline, showOnTimeline } from "../manual/EditLanes";
import { selectInText } from "../manual/TranscriptEdit";
import type { Episode } from "../../api";
import type { Player } from "../../usePlayer";
import { t } from "../../i18n";

/** Where the tour's spots are on the current cut (GET …/tour/marks), seconds. */
export interface Marks {
  hosts: [string, string];
  actor: [number, number] | null;
  water: [number, number] | null;
  gap: [number, number] | null;
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
  ch: number; // chapter 1-7
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
  /** lit up while `result` shows (default: `target`): where the outcome is */
  resultTarget?: Target[];
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

export const CHAPTERS = 7;
export const chapterName = (n: number) =>
  [t("先听原始录音"), t("审阅改动"), t("整集试听"), t("声音"), t("配乐"), t("导出"), t("发布")][n - 1] ?? "";

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
/** LACUNA's suggestion; once approved, the message saying so */
const proposalOrApproved = () => {
  const p = q('[data-testid="proposal"]');
  const ok = [...document.querySelectorAll(".pstate.ok")].pop()?.closest(".msg");
  return p ? [p] : ok ? [ok] : [];
};
const intro = '[data-testid="placement"][data-role="intro"]';

export const TOUR_CHAT = () => t("把阿乔问演员名字的那两句删掉");
export const TOUR_MUSIC = () => t("说话时片头音乐再小一点");

export const STEPS: Step[] = [
  // 1 the raw recording: a dialog of its own (Tour.tsx)
  { id: "raw", ch: 1, mode: "review", title: () => t("先听听没剪过的样子"), body: () => t("这是示例节目开头 30 秒的原始录音：有重说、口头禅、冷场，两人一个大声一个小声。点 **▶ 播放原始录音** 听一听，放完自动进入下一步；教程最后会放剪好的同一段给你对比。") },

  // 2 审阅改动
  { id: "rlist", ch: 2, mode: "review", side: "right", target: [".review-nav"],
    title: () => t("LACUNA 拿不准的 3 处"),
    body: () => t("LACUNA 已经剪完了第一版。大部分改动它有把握，左边只列出它拿不准的 **3 处**，等你审阅。停顿、口头禅这些小改动，整集试听时都能听到。") },
  { id: "rab", ch: 2, mode: "review", side: "bottom", target: [".rv-act .ab-seg"],
    act: async (c) => {
      await hear(c, ".rv-act .ab-opt:nth-of-type(1)");
      await wait(400);
      await hear(c, ".rv-act .ab-opt:nth-of-type(2)");
    },
    title: () => t("先听，再决定"),
    body: (h) => t("第 1 处：{a}开头把一句话重说了一遍。按 **知道了**，LACUNA 先放 **A · 原话**（删之前），再放 **B · 剪后**（删之后）。", h),
    hint: () => t("正在播放…") },
  { id: "rdecide", ch: 2, mode: "review", side: "top", target: [".rv-act .btn-outline", ".rv-act .btn-primary"],
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

  // 3 整集试听: three ways to cut (Leon 2026-10-23 prototype): tell LACUNA, delete words, cut on the timeline
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
    title: () => t("第一种：直接跟 LACUNA 说"),
    body: (h) => t("这是整集试听：边听边改，有三种剪法。第一种最省事，直接告诉 LACUNA 你想怎么改。虚线框里，{b}想不起演员名字，来回两句，中间还冷场了。按 **知道了**，LACUNA 替你写一句「{text}」并发送。", { ...h, text: TOUR_CHAT() }),
    hint: () => t("LACUNA 正在回答…"),
    result: () => t("LACUNA 找到了那一段，给了一个改法，还没动你的音频。") },
  { id: "cab", ch: 3, mode: "listen", side: "left", target: [proposalOrApproved], resultTarget: ['[data-testid="edit-lanes"]'],
    act: async (c) => {
      await tap('[data-testid="proposal"] .btn-outline-accent');
      await until(() => q('[data-testid="proposal"] .ab button'));
      await hear(c, '[data-testid="proposal"] .ab button:nth-of-type(1)');
      await wait(400);
      await hear(c, '[data-testid="proposal"] .ab button:nth-of-type(2)');
      await wait(600);
      if (c.alive()) await tap('[data-testid="proposal"] .btn-primary');
    },
    done: () => !q('[data-testid="proposal"]') && !!q(".pstate.ok"),
    title: () => t("批准前，你可以先听一下"),
    body: () => t("LACUNA 不会直接改。**▶ 现在** 是原样，**▶ 改后** 是删掉这两句以后。按 **知道了**，LACUNA 先各放一遍，再替你点 **批准**。"),
    hint: () => t("正在播放，听完批准…"),
    result: () => t("批准了：那两句删掉了，时间线上多了一条橙色剪切线。") },
  { id: "tcut", ch: 3, mode: "listen", side: "top", target: ['[data-testid="transcript-edit"]'],
    enter: (c) => {
      const w = c.marks?.water;
      if (w) { c.player.seek(Math.max(0, w[0] - 1)); showOnTimeline(w[0] - 2, w[1] + 2); }
      q('[data-testid="transcript-edit"]')?.scrollIntoView({ block: "center" });
    },
    act: async (c) => {
      c.memo.n = manual(c.ep, false);
      const w = c.marks?.water;
      if (w) selectInText(w[0] - 0.05, w[1] + 0.05);
      const cut = '[data-testid="transcript-edit"] [data-testid="ml-cut"]';
      await until(() => q(cut), 3000);
      await wait(900);
      await tap(cut);
    },
    done: (c) => manual(c.ep, false) > Number(c.memo.n ?? 0),
    title: () => t("第二种：像改文档一样剪"),
    body: (h) => t("在逐字稿里选中一段字、删掉，对应的声音就剪掉了；删过的字显示删除线，点一下就能恢复。{a}说的「等一下，我喝口水」这句不要。按 **知道了**，LACUNA 替你选中这句，点 **删掉这段**。", h),
    hint: () => t("正在删…"),
    result: () => t("删掉了：这句变成删除线，时间线上也多了一条剪切线。") },
  { id: "dgap", ch: 3, mode: "listen", side: "bottom", target: [".ml .ml-body"],
    enter: (c) => {
      const g = c.marks?.gap;
      if (g) { c.player.seek(Math.max(0, g[0] - 3)); showOnTimeline(g[0] - 2, g[1] + 2); }
      q(".ml .ml-body")?.scrollIntoView({ block: "center" });
    },
    box: (c) => (c.marks?.gap ? { track: c.marks.hosts[0], a: c.marks.gap[0], b: c.marks.gap[1] } : null),
    act: async (c) => {
      c.memo.n = manual(c.ep, false);
      const g = c.marks?.gap;
      if (g) selectOnTimeline(g[0] + 0.1, g[1] - 0.15);
      await until(() => q('[data-testid="ml-cut"]'), 3000);
      await wait(900);
      await tap('[data-testid="ml-cut"]');
    },
    done: (c) => manual(c.ep, false) > Number(c.memo.n ?? 0),
    title: () => t("第三种：没字的地方，在时间线上剪"),
    body: () => t("每人一条轨道，**橙色竖线** 是剪切点。喝完水还有一段冷场（虚线框），没有字，逐字稿里删不了。平时在轨道上 **按住鼠标** 拖选它，再点 **删掉这段**；咳嗽这种只有一个人的声音，可以 **只静音** 那个人。按 **知道了**，LACUNA 替你剪掉这段冷场。"),
    hint: () => t("正在剪…"),
    result: () => t("剪好了。这三种剪法剪掉的，都能在这里随时恢复。") },

  // 4 声音
  { id: "vauto", ch: 4, mode: "levels", side: "bottom", target: [".levels-card"],
    act: (c) => tap('[data-tour="levels-auto"]').then(() => until(() => !q('[data-tour="levels-auto"][disabled]') || !c.alive())),
    title: () => t("一个大声，一个小声"),
    body: (h) => t("{a}离麦克风近，比{b}响很多。尺子上白线是原始音量，彩色条是现在，绿线是目标。按 **知道了**，LACUNA 替你点 **统一主持人音量**，两人都到绿线。", h),
    hint: () => t("正在统一音量…") },

  // 5 配乐
  { id: "uput", ch: 5, mode: "music", side: "right", target: ['[data-tour="music-library"]'],
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
  { id: "usend", ch: 5, mode: "music", side: "top", target: ['[data-tour="music-assist"]'], resultTarget: [`${intro} [data-testid="music-curve"]`],
    // the request is about the intro, so its curve is the one open on screen
    enter: () => {
      const tg = q(`${intro} .mcard-toggle`) as HTMLButtonElement | null;
      if (tg?.getAttribute("aria-expanded") === "false") tg.click();
    },
    act: async (c) => {
      await type(c, '[data-tour="music-assist"] textarea', TOUR_MUSIC());
      await wait(500);
      await tap('[data-tour="music-assist"] .btn-primary');
      await until(() => q('[data-testid="music-draft"]'), 15_000);
      await wait(1500);
      await tap('[data-testid="music-draft"] .btn-primary');
    },
    done: () => !q('[data-testid="music-draft"]'),
    title: () => t("配乐的位置和音量，直接说"),
    body: () => t("放好的音乐，想调位置、音量、淡入淡出，直接说就行。用哪首曲子，还是你在素材库里挑。LACUNA 的改动先变成建议，满意再 **采用**。按 **知道了**，LACUNA 替你发一句「{text}」，再点采用。", { text: TOUR_MUSIC() }),
    hint: () => t("LACUNA 正在调…"),
    result: () => t("采用了：有人说话时，片头音乐又压低了 4 dB，曲线里压低的那一段往下掉了。") },

  // 6 导出
  { id: "xstart", ch: 6, mode: "export", side: "bottom", target: ['[data-tour="export-formats"]', '[data-tour="export-start"]', ".xmain .job"],
    act: () => tap('[data-tour="export-start"]'),
    done: () => !!q('[data-testid="export-result"]'),
    title: () => t("导出"),
    body: () => t("**MP3** 体积小，适合分享；**WAV** 音质最好。按 **知道了**，LACUNA 替你点 **开始导出**：整集重新合成，再统一响度。要多久看节目长短，长的节目要等几分钟。"),
    hint: () => t("正在导出…") },
  { id: "xsum", ch: 6, mode: "export", side: "left", target: ['[data-tour="export-summary"]', '[data-tour="export-standard"]'],
    title: () => t("这一集的结果"),
    body: () => t("原始多长、成品多长、剪掉多少、配乐几处，都在这里。响度统一到 −16 LUFS，真峰值不超过 −1 dBTP，符合 Apple Podcasts、Spotify 等平台的标准，可以直接上传。") },

  // 7 发布
  { id: "ptext", ch: 7, mode: "publish", side: "bottom", target: ['[data-tour="publish-title-card"]', '[data-tour="publish-generate"]'],
    act: async () => {
      if (!q('[data-testid="publish-title"]')) await tap('[data-tour="publish-generate"]');
    },
    done: () => !!q('[data-testid="publish-title"]') && !!q('[data-testid="show-notes"]'),
    title: () => t("发布资料"),
    body: () => t("按 **知道了**，LACUNA 读剪好的逐字稿，写这一集的标题、一句话简介和带时间戳的 show notes。"),
    hint: () => t("LACUNA 正在写…"),
    result: () => t("写好了：标题、备选标题、简介和 show notes，点一下就能复制，和导出的音频一起贴到播客平台。剪辑再改，时间戳一键更新。") },
  { id: "pposter", ch: 7, mode: "poster", side: "bottom", target: ['[data-testid="poster-card"]', '[data-tour="poster-generate"]'],
    act: async () => {
      if (!q('[data-testid="poster-card"]')) await tap('[data-tour="poster-generate"]');
    },
    done: () => !!q('[data-testid="poster-card"]'),
    title: () => t("封面"),
    body: () => t("按 **知道了**，LACUNA 按标题和简介画几版方形封面。"),
    hint: () => t("LACUNA 正在画…"),
    result: () => t("挑一张就能用；不满意，说一句话让它改。示例就到这里，最后听一下剪前剪后的对比。") },
];

export const DONE = "done";
