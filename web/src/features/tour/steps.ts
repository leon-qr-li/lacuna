// The bubble tour of LACUNA 示例节目 (new-user batch, tour v3, canvas boards U00–U60): every page the way a
// host really uses it, one bubble per thing, the thing it talks about lit up. A locked demo (Leon 2026-10-23):
// LACUNA does each step itself in its `enter` (clicks, selects, sends); the person only presses 知道了, which
// waits for `done` while LACUNA is still at it.
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
  body: (h: Hosts) => string; // **bold**
  /** lit up (their union); nothing found → the bubble sits in the middle */
  target?: Target[];
  /** LACUNA is done with the step: until then 知道了 waits and shows `hint` */
  done?: (c: Ctx) => boolean;
  hint?: (h: Hosts) => string;
  /** what LACUNA does on the step, once its page and marks are there */
  enter?: (c: Ctx) => void | Promise<void>;
  side?: "top" | "bottom" | "left" | "right";
  /** the bubble keeps clear of these too (default: only the lit part) */
  around?: string[];
  /** a dashed box on the timeline: where to drag (track null = all tracks) */
  box?: (c: Ctx) => { track: string | null; a: number; b: number } | null;
}

export type Hosts = Record<string, string> & {
  a: string;
  b: string;
};

export const CHAPTERS = 10;
export const chapterName = (n: number) =>
  [t("先听原始录音"), t("审阅改动"), t("整集试听"), t("对 LACUNA 说"), t("手动删除"), t("手动静音"), t("声音"), t("配乐"), t("导出"), t("发布")][n - 1] ?? "";

const q = (sel: string) => document.querySelector(sel);
const click = (sel: string) => (q(sel) as HTMLElement | null)?.click();
/** Type into a React-controlled textarea / input */
export function fill(sel: string, text: string) {
  const el = q(sel) as HTMLTextAreaElement | HTMLInputElement | null;
  if (!el) return;
  const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value")?.set?.call(el, text);
  el.dispatchEvent(new Event("input", { bubbles: true }));
}
/** m:ss.s → seconds */
const secs = (s: string) => {
  const m = /(\d+):(\d+(?:\.\d+)?)/.exec(s);
  return m ? Number(m[1]) * 60 + Number(m[2]) : NaN;
};
/** the transcript lines starting inside [a, b] */
const lines = (a: number, b: number) =>
  [...document.querySelectorAll(".ml-tx .ml-line")].filter((el) => {
    const s = secs(el.querySelector(".ml-t")?.textContent ?? "");
    return s >= a - 0.4 && s <= b;
  });
const routine = (ep: Episode) => ep.edits.find((e) => e.ai_category === "disfluency" && e.source === "first_cut");
const manual = (ep: Episode, lift: boolean) => ep.edits.filter((e) => e.source === "manual" && !!e.tracks === lift).length;
const wait = (ms: number) => new Promise((r) => window.setTimeout(r, ms));
/** waits until f() is true, at most ms */
const until = async (f: () => unknown, ms = 10_000) => {
  const end = Date.now() + ms;
  while (!f() && Date.now() < end) await wait(100);
  return !!f();
};
const playing = () => [...document.querySelectorAll("audio")].some((a) => !a.paused);
/** LACUNA clicks a play button and waits until it has played (at most ms) */
const hear = async (c: Ctx, sel: string, ms = 9000) => {
  if (!c.alive()) return;
  click(sel);
  await until(playing, 2000);
  await until(() => !playing() || !c.alive(), ms);
};
/** an enter that does `act` after a short look, then marks the step done */
const doing = (act: (c: Ctx) => Promise<unknown> | unknown, first = 900) => async (c: Ctx) => {
  await wait(first);
  if (!c.alive()) return;
  await act(c);
  c.memo.done = true;
};
const did = (c: Ctx) => !!c.memo.done;
const findBtn = (sel: string, re: RegExp) => [...document.querySelectorAll<HTMLElement>(sel)].find((b) => re.test(b.textContent ?? ""));
const intro = '[data-testid="placement"][data-role="intro"]';
const openIntro = () => {
  const b = q(`${intro} [data-testid="placement-toggle"]`);
  if (b?.getAttribute("aria-expanded") === "false") (b as HTMLElement).click();
};

export const TOUR_CHAT = () => t("把阿乔问演员名字的那两句删掉");
export const TOUR_MUSIC = () => t("说话时片头音乐再小一点");

export const STEPS: Step[] = [
  // 1 the raw recording: a dialog of its own (Tour.tsx)
  { id: "raw", ch: 1, mode: "review", title: () => t("先听听没剪过的样子"), body: () => t("这是示例节目开头 30 秒的原始录音：有重说、口头禅、冷场，两人一个大声一个小声。教程最后会放剪好的同一段给你对比。") },

  // 2 审阅改动
  { id: "rlist", ch: 2, mode: "review", side: "right", target: ['[data-testid="review-list"]'],
    title: () => t("先看左边的清单"),
    body: () => t("LACUNA 剪第一刀时，把 **3 处**拿不准、可能删错内容的地方挑出来，排在这里等你过目。现在选中的是第 1 处。") },
  { id: "rab", ch: 2, mode: "review", side: "bottom", target: [".rv-act .ab-seg"],
    enter: doing(async (c) => {
      await hear(c, ".rv-act .ab-opt:nth-of-type(1)");
      await wait(400);
      await hear(c, ".rv-act .ab-opt:nth-of-type(2)");
    }),
    done: did,
    title: () => t("先听，再决定"),
    body: () => t("LACUNA 先放 **A · 原话**（删之前），再放 **B · 剪后**（删之后）。平时你自己点这两个按钮对比。"),
    hint: () => t("正在播放…") },
  { id: "rdecide", ch: 2, mode: "review", side: "top", target: [".review-main", '[data-testid="review-list"]'],
    enter: doing(async (c) => {
      for (let i = 0; i < 3 && c.alive(); i++) {
        await until(() => findBtn(".rv-act button.btn-primary", /K/));
        findBtn(".rv-act button.btn-primary", /K/)?.click();
        await wait(1300);
      }
    }, 1500),
    done: (c) => did(c) && (c.ep.pending_review ?? 0) === 0,
    title: () => t("保留，还是恢复？"),
    body: () => t("删得对就点 **保留**（键盘 K）；想留原话就点 **恢复原话**（R）。删除早已生效，你只是确认。这 3 处 LACUNA 都删对了，它替你一处处点了 **保留**。"),
    hint: () => t("正在确认 3 处…") },
  { id: "rroutine", ch: 2, mode: "review", side: "right", target: ['[data-testid="review-routine"]'],
    title: () => t("还有 2 处是自动剪的"),
    body: () => t("一个口头禅、一段冷场，LACUNA 直接剪好了，不用一处处看。剪得不对也能恢复，下一章就教你。") },

  // 3 整集试听
  { id: "llanes", ch: 3, mode: "listen", side: "bottom", target: ['[data-testid="edit-lanes"]'],
    enter: (c) => c.player.seek(0),
    title: () => t("剪辑时间线"),
    body: () => t("每人一条轨道，波形就是说话的声音。**橙色竖线**是剪切点，这一集只有 5 处。按播放会从头放剪好的版本。") },
  { id: "lpop", ch: 3, mode: "listen", side: "bottom", target: [".ml .ml-body"],
    enter: async (c) => {
      const e = routine(c.ep);
      if (!e) return void (c.memo.done = true);
      c.player.seek(Math.max(0, e.t - 2));
      showOnTimeline(e.t - 2, e.t + 1);
      await doing(() => click(`.ml-gone[data-edit="${e.id}"]`), 2500)(c);
    },
    box: (c) => {
      const e = routine(c.ep);
      return e ? { track: c.ep.tracks[0]?.name ?? null, a: e.t - 0.4, b: e.t + 0.4 } : null;
    },
    done: (c) => did(c) && routine(c.ep)?.status !== "applied",
    title: () => t("自动剪的，也能恢复"),
    body: () => t("虚线框里那条橙色竖线，是自动剪掉的口头禅「呃」。平时把鼠标移上去，弹出卡片后点 **恢复**。这次 LACUNA 替你恢复了它。"),
    hint: () => t("正在恢复…") },

  // 4 对 LACUNA 说
  { id: "ctx", ch: 4, mode: "listen", side: "top",
    enter: (c) => {
      click('[data-testid="tab-ai"]');
      if (c.marks?.actor) { c.player.seek(c.marks.actor[0]); showOnTimeline(c.marks.actor[0], c.marks.actor[1]); }
    },
    target: [(c) => (c.marks?.actor ? lines(c.marks.actor[0], c.marks.actor[1]) : [])],
    title: () => t("这两句有点拖"),
    body: (h) => t("{b}想不起演员名字，来回两句，中间还冷场了。这种地方，直接跟 LACUNA 说就能剪。", h) },
  { id: "cprompt", ch: 4, mode: "listen", side: "left", target: ["form.chat-form"],
    enter: () => {
      click('[data-testid="tab-ai"]');
      window.setTimeout(() => fill("form.chat-form textarea", TOUR_CHAT()), 50);
    },
    title: () => t("用一句话让 LACUNA 剪"),
    body: () => t("平时你在这里打字。示例里已经替你填好：「{text}」。**@ 时间** 表示说的是播放头这里。", { text: TOUR_CHAT() }) },
  { id: "csend", ch: 4, mode: "listen", side: "top", target: ["form.chat-form button.btn-primary"], around: ["form.chat-form"],
    enter: doing(() => {
      const el = q("form.chat-form textarea") as HTMLTextAreaElement | null;
      if (el && !el.value.trim()) fill("form.chat-form textarea", TOUR_CHAT());
      return wait(200).then(() => click("form.chat-form button.btn-primary"));
    }, 1500),
    done: (c) => did(c) && c.ep.proposals.length > 0,
    title: () => t("发送"),
    body: () => t("LACUNA 替你点了 **发送**，看它怎么回答。"),
    hint: () => t("LACUNA 正在回答…") },
  { id: "cab", ch: 4, mode: "listen", side: "left", target: ['[data-testid="proposal"]'],
    enter: doing(async (c) => {
      click('[data-testid="proposal"] .btn-outline-accent');
      await until(() => q('[data-testid="proposal"] .ab button'));
      await hear(c, '[data-testid="proposal"] .ab button:nth-of-type(1)');
      await wait(400);
      await hear(c, '[data-testid="proposal"] .ab button:nth-of-type(2)');
    }),
    done: did,
    title: () => t("先听，再批准"),
    body: () => t("LACUNA 不会直接改，先给你听：**▶ 现在** 是原样，**▶ 改后** 是删掉这两句以后。"),
    hint: () => t("正在播放…") },
  { id: "cok", ch: 4, mode: "listen", side: "left", target: ['[data-testid="proposal"]', ".pstate.ok"],
    enter: doing(() => click('[data-testid="proposal"] .btn-primary'), 1200),
    done: () => !q('[data-testid="proposal"]') && !!q(".pstate.ok"),
    title: () => t("满意就批准"),
    body: (h) => t("LACUNA 替你点了 **批准**，{b}这两句删掉了。不满意的话，平时可以点「再改」接着说。", h),
    hint: () => t("正在批准…") },

  // 5 手动删除
  // LACUNA selects and cuts it for the user (Leon 2026-10-23: a drag is too much to ask here)
  { id: "dlanes", ch: 5, mode: "listen", side: "bottom", target: [".ml .ml-body"],
    enter: async (c) => {
      const w = c.marks?.water;
      if (!w) return void (c.memo.done = true);
      c.player.seek(Math.max(0, w[0] - 3));
      showOnTimeline(w[0] - 1, w[1] + 1);
      await doing(() => selectOnTimeline(w[0], w[1]), 1200)(c);
    },
    box: (c) => (c.marks?.water ? { track: c.marks.hosts[0], a: c.marks.water[0], b: c.marks.water[1] } : null),
    done: (c) => did(c) && (!c.marks?.water || !!q('[data-testid="ml-sel"]')),
    title: () => t("自己动手删一段"),
    body: (h) => t("{a}说「等一下，我喝口水」，这句不要。平时在轨道上 **按住鼠标** 从左拖到右选中它；这次 LACUNA 替你选好了。", h),
    hint: () => t("正在选中…") },
  { id: "dcut", ch: 5, mode: "listen", side: "bottom", target: [".ml .ml-body"],
    enter: doing(async (c) => {
      c.memo.n = manual(c.ep, false);
      click('[data-testid="ml-cut"]');
    }, 600),
    done: (c) => did(c) && manual(c.ep, false) > Number(c.memo.n ?? 0),
    title: () => t("删掉这段"),
    body: () => t("LACUNA 替你点了菜单里的 **删掉这段**，这句已经删掉了。删错了按 Ctrl + Z 撤销。"),
    hint: () => t("正在删…") },

  // 6 手动静音
  { id: "mlanes", ch: 6, mode: "listen", side: "bottom", target: [".ml .ml-body"],
    enter: async (c) => {
      const k = c.marks?.cough;
      if (!k) return void (c.memo.done = true);
      c.player.seek(Math.max(0, k[0] - 3));
      showOnTimeline(k[0] - 1, k[1] + 1);
      await doing(() => selectOnTimeline(k[0] - 0.05, k[1] + 0.05), 1200)(c);
    },
    box: (c) => (c.marks?.cough ? { track: c.marks.hosts[0], a: c.marks.cough[0] - 0.1, b: c.marks.cough[1] + 0.1 } : null),
    done: (c) => did(c) && (!c.marks?.cough || !!q('[data-testid="ml-sel"]')),
    title: (h) => t("{b}说话时，{a}咳了一声", h),
    body: (h) => t("删掉整段会把{b}的话也删了。LACUNA 先选中咳嗽那一小段（橙色虚线框）。", h),
    hint: () => t("正在选中…") },
  { id: "mmute", ch: 6, mode: "listen", side: "bottom", target: ['[data-testid="ml-menu"]', '[data-testid="ml-sel"]'],
    enter: doing((c) => {
      c.memo.n = manual(c.ep, true);
      click(`[data-testid="ml-mute-${c.marks?.hosts[0] ?? ""}"]`);
    }, 1800),
    done: (c) => did(c) && manual(c.ep, true) > Number(c.memo.n ?? 0),
    title: () => t("只静音一个人"),
    body: (h) => t("菜单里有 **只静音 {a}**：{b}的话留着，只把{a}那条轨道的这一下变安静。LACUNA 替你点了它。", h),
    hint: () => t("正在静音…") },
  { id: "mstripe", ch: 6, mode: "listen", side: "bottom",
    box: (c) => (c.marks?.cough ? { track: c.marks.hosts[0], a: c.marks.cough[0] - 0.3, b: c.marks.cough[1] + 0.3 } : null),
    target: [(c) => [...document.querySelectorAll(`[data-testid="lane-${c.marks?.hosts[0] ?? c.ep.tracks[0]?.name}"]`)]],
    title: () => t("斜线 = 只删了一个人"),
    body: (h) => t("{a}的轨道上出现斜线，表示这里只静音了{a}。把鼠标移上去也能恢复。", h) },

  // 7 声音
  { id: "vauto", ch: 7, mode: "levels", side: "bottom", target: ['[data-tour="levels-auto"]'],
    enter: doing(() => click('[data-tour="levels-auto"]'), 1500),
    done: (c) => did(c) && !q('[data-tour="levels-auto"][disabled]'),
    title: () => t("一个大声，一个小声"),
    body: (h) => t("{a}离麦克风近，比{b}响很多。LACUNA 替你点了 **统一两人音量**，把两人都调到同一个响度。", h),
    hint: () => t("正在统一音量…") },
  { id: "vmeter", ch: 7, mode: "levels", side: "bottom", target: [".levels-tracks .levels-top"],
    title: () => t("看这把尺子"),
    body: () => t("白线是原始音量，彩色条是现在，绿线是目标。统一后两人的彩色条都到了绿线，右边的波形也一样高了。") },

  // 8 配乐
  { id: "uintro", ch: 8, mode: "music", side: "right", target: ['[data-tour="music-asset-intro"]', ".mlib-menu"],
    enter: doing(async () => {
      if (q(intro)) return;
      click('[data-tour="music-asset-intro"] .mlib-put');
      await wait(900);
      click('[data-tour="music-asset-intro"] .mlib-menu [role="menuitem"]:nth-of-type(1)');
    }),
    done: (c) => did(c) && !!q(intro),
    title: () => t("放上片头"),
    body: () => t("LACUNA 点开第一首的 **放到 ▾**，选了 **片头**。"),
    hint: () => t("正在放片头…") },
  { id: "uoutro", ch: 8, mode: "music", side: "right", target: ['[data-tour="music-asset-outro"]', ".mlib-menu"],
    enter: doing(async () => {
      if (q('[data-testid="placement"][data-role="outro"]')) return;
      click('[data-tour="music-asset-outro"] .mlib-put');
      await wait(900);
      click('[data-tour="music-asset-outro"] .mlib-menu [role="menuitem"]:nth-of-type(2)');
    }),
    done: (c) => did(c) && !!q('[data-testid="placement"][data-role="outro"]'),
    title: () => t("再放片尾"),
    body: () => t("第二首放到 **片尾**。"),
    hint: () => t("正在放片尾…") },
  { id: "ucurve", ch: 8, mode: "music", side: "left", target: [`${intro} [data-testid="music-curve"]`],
    enter: openIntro,
    title: () => t("这条线是音乐的音量"),
    body: () => t("点开片头卡片，就能看到：淡入 → 开头只放音乐 → 有人开口时自动压低 → 最后淡出。底下的色块是有人说话的地方。") },
  { id: "usend", ch: 8, mode: "music", side: "top", target: ['[data-tour="music-assist"]'],
    enter: doing(async () => {
      fill('[data-tour="music-assist"] textarea', TOUR_MUSIC());
      await wait(1200);
      click('[data-tour="music-assist"] .btn-primary');
    }, 300),
    done: (c) => did(c) && !!q('[data-testid="music-draft"]'),
    title: () => t("说一句，让 LACUNA 调"),
    body: () => t("不想自己调数值，也可以直接说。LACUNA 替你发了一句：「{text}」。", { text: TOUR_MUSIC() }),
    hint: () => t("LACUNA 正在调…") },
  { id: "uadopt", ch: 8, mode: "music", side: "bottom", target: ['[data-testid="music-draft"]'],
    enter: doing(() => click('[data-testid="music-draft"] .btn-primary'), 2500),
    done: (c) => did(c) && !q('[data-testid="music-draft"]'),
    title: () => t("采用，还是不要"),
    body: () => t("LACUNA 的改动先变成建议，可以点 **试听**。满意就点 **采用**，片头卡片上的曲线会跟着变；不满意就点「不要」。这次替你点了采用。"),
    hint: () => t("正在采用…") },

  // 9 导出
  { id: "xstart", ch: 9, mode: "export", side: "bottom", target: ['[data-tour="export-start"]', ".xmain .job"],
    enter: doing(() => click('[data-tour="export-start"]'), 1200),
    done: (c) => did(c) && !!q('[data-testid="export-result"]'),
    title: () => t("开始导出"),
    body: () => t("LACUNA 替你点了 **开始导出**：整集重新合成，再统一响度。要多久看节目长短，长的节目要等几分钟，进度条走完就好。"),
    hint: () => t("正在导出…") },
  { id: "xsum", ch: 9, mode: "export", side: "left", target: ['[data-tour="export-summary"]'],
    title: () => t("这一集的结果"),
    body: () => t("右边是这一集的结果：原始多长、成品多长、剪掉多少、配乐几处、两人音量是否已统一。") },
  { id: "xstd", ch: 9, mode: "export", side: "left", target: ['[data-tour="export-standard"]'],
    title: () => t("符合播客平台标准"),
    body: () => t("响度统一到 −16 LUFS，真峰值不超过 −1 dBTP，这是 Apple Podcasts、Spotify 等平台的标准，可以直接上传。") },

  // 10 发布
  { id: "ptext", ch: 10, mode: "publish", side: "bottom", target: ['[data-tour="publish-title-card"]', '[data-tour="publish-generate"]'],
    enter: doing(() => {
      if (!q('[data-testid="publish-title"]')) click('[data-tour="publish-generate"]');
    }, 1200),
    done: (c) => did(c) && !!q('[data-testid="publish-title"]'),
    title: () => t("标题和简介"),
    body: () => t("LACUNA 读剪好的文字稿，写好了这一集的标题、几个备选标题和一句话简介，点一下就能复制。"),
    hint: () => t("LACUNA 正在写…") },
  { id: "pnotes", ch: 10, mode: "publish", side: "top", target: ['[data-testid="show-notes"]'],
    title: () => t("Show notes 和章节"),
    body: () => t("Show notes 带时间戳，按话题分好段，和导出的音频一起贴到播客平台就行。剪辑再改，时间戳一键更新。") },
  { id: "pposter", ch: 10, mode: "poster", side: "bottom", target: ['[data-testid="poster-card"]', '[data-tour="poster-generate"]'],
    enter: doing(() => {
      if (!q('[data-testid="poster-card"]')) click('[data-tour="poster-generate"]');
    }, 1200),
    done: (c) => did(c) && !!q('[data-testid="poster-card"]'),
    title: () => t("海报"),
    body: () => t("LACUNA 按标题和简介画了几版方形封面，挑一张就能用；不满意，说一句话让它改。示例就到这里，最后听一下前后对比。"),
    hint: () => t("LACUNA 正在画…") },
];

export const DONE = "done";
