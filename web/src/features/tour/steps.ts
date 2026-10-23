// The bubble tour of LACUNA 示例节目 (new-user batch, tour v3, canvas boards U00–U60): every page the way a
// host really uses it, one bubble per thing, the thing it talks about lit up. A "do" step waits until it has
// been done (only the lit part can be clicked); the others have 知道了.
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
  /** what a step noted when it began (a count, a label) */
  memo: Record<string, unknown>;
  /** selectors of the step's `clicks` that have been clicked */
  clicked: Set<string>;
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
  /** a do step: done when this is true (and every `clicks` selector was clicked) */
  done?: (c: Ctx) => boolean;
  clicks?: string[];
  hint?: (h: Hosts) => string;
  /** a 知道了 step whose lit part can still be clicked (try it, or not) */
  free?: boolean;
  /** a do step that may also be passed with 知道了 */
  alsoOk?: boolean;
  enter?: (c: Ctx) => void;
  /** notes what the step compares against, the moment it begins (before anything can be clicked) */
  init?: (c: Ctx) => void;
  side?: "top" | "bottom" | "left" | "right";
  /** a dashed box on the timeline: where to drag (track null = all tracks) */
  box?: (c: Ctx) => { track: string | null; a: number; b: number } | null;
}

export type Hosts = Record<string, string> & {
  a: string;
  b: string;
};

export const CHAPTERS = 9;
export const chapterName = (n: number) =>
  [t("先听原始录音"), t("审阅改动"), t("整集试听"), t("对 LACUNA 说"), t("手动删除"), t("手动静音"), t("声音"), t("配乐"), t("导出")][n - 1] ?? "";

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
/** a lanes selection covering at least half of [a, b] */
const selOver = (span: [number, number] | null | undefined) => {
  const s = q('[data-testid="ml-sel"]') as HTMLElement | null;
  if (!s || !span) return false;
  const a = Number(s.dataset.a);
  const b = Number(s.dataset.b);
  const [x, y] = span;
  return Math.max(0, Math.min(b, y) - Math.max(a, x)) >= (y - x) * 0.5;
};
const isMode = (m: string) => (c: Ctx) => c.mode === m;
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
  { id: "rbody", ch: 2, mode: "review", side: "bottom", target: [".rv-card .rv-head", ".rv-reason", ".rv-lines"],
    title: () => t("这一处删了什么"),
    body: () => t("最上面是删了什么、删了多久；下面一行是 LACUNA 删它的理由；再下面是前后文，**删除线**就是被删掉的话。") },
  { id: "rab", ch: 2, mode: "review", side: "bottom", target: [".rv-act .ab-seg"],
    clicks: [".rv-act .ab-opt:nth-of-type(1)", ".rv-act .ab-opt:nth-of-type(2)"],
    done: () => true,
    title: () => t("先听，再决定"),
    body: () => t("点 **A · 原话** 听删之前，再点 **B · 剪后** 听删之后。"),
    hint: () => t("两个都听过后继续") },
  { id: "rspeed", ch: 2, mode: "review", side: "bottom", free: true, target: ['[data-testid="review-speed"]'],
    title: () => t("嫌慢可以倍速"),
    body: () => t("点 **1×** 切到 1.5× 听，音调不变。整集试听里也一样。") },
  { id: "rdecide", ch: 2, mode: "review", side: "top", target: [".review-main", '[data-testid="review-list"]'],
    done: (c) => (c.ep.pending_review ?? 0) === 0,
    title: () => t("保留，还是恢复？"),
    body: () => t("删得对就点 **保留**（键盘 K）；想留原话就点 **恢复原话**（R）。删除早已生效，你只是确认。后面 2 处也一样：先听 A/B，再决定。"),
    hint: () => t("3 处都决定后继续") },
  { id: "rprog", ch: 2, mode: "review", side: "bottom", target: ['[data-testid="review-progress"]'],
    title: () => t("3 处都看完了"),
    body: () => t("这里显示看了几处。处数多时，右边的 **剩下的全部保留** 能一键确认其余的，也能一步撤销。旁边的 **?** 是全部快捷键。") },
  { id: "rroutine", ch: 2, mode: "review", side: "right", target: ['[data-testid="review-routine"]'],
    title: () => t("还有 2 处是自动剪的"),
    body: () => t("一个口头禅、一段冷场，LACUNA 直接剪好了，不用一处处看。剪得不对也能恢复，下一章就教你。") },
  { id: "rnext", ch: 2, mode: "review", side: "bottom", target: ['[data-testid="next-step"]'], done: isMode("listen"),
    title: () => t("进入整集试听"),
    body: () => t("审阅做完了。点右上角 **下一步：整集试听**，从头听一遍整集。"),
    hint: () => t("点「下一步」") },

  // 3 整集试听
  { id: "llanes", ch: 3, mode: "listen", side: "bottom", target: ['[data-testid="edit-lanes"]'],
    enter: (c) => c.player.seek(0),
    title: () => t("剪辑时间线"),
    body: () => t("每人一条轨道，波形就是说话的声音。**橙色竖线**是剪切点，这一集只有 5 处。按播放会从头放剪好的版本。") },
  { id: "llegend", ch: 3, mode: "listen", side: "bottom", target: ['[data-testid="ml-legend"]'],
    title: () => t("图例"),
    body: () => t("剪切点、单轨删减（只删一个人）、已恢复、待批准、你选中的，在时间线上分别长这样。") },
  { id: "lplayer", ch: 3, mode: "listen", side: "top", free: true, target: ["section.player"],
    title: () => t("播放条"),
    body: () => t("**−5s / +5s** 前后跳，**1× / 1.5×** 切倍速；勾上 **暂停时回退 5 秒**，每次暂停后会往回退一点，方便重听。空格键也能播放 / 暂停。") },
  { id: "lpop", ch: 3, mode: "listen", side: "bottom", target: [".ml .ml-body", '[data-testid="ml-pop"]'],
    enter: (c) => {
      const e = routine(c.ep);
      if (e) c.player.seek(Math.max(0, e.t - 4));
    },
    box: (c) => {
      const e = routine(c.ep);
      return e ? { track: c.ep.tracks[0]?.name ?? null, a: e.t - 0.4, b: e.t + 0.4 } : null;
    },
    done: (c) => routine(c.ep)?.status === "restored",
    title: () => t("自动剪的，也能恢复"),
    body: () => t("把鼠标移到虚线框里那条橙色竖线上，这是自动剪掉的口头禅「呃」。弹出卡片后先点 **▶ 听前后**，再点 **恢复**。"),
    hint: () => t("点「恢复」后继续") },
  { id: "ltx", ch: 3, mode: "listen", side: "top", target: [(c) => { const e = routine(c.ep); return e ? lines(e.t - 8, e.t + 0.5).slice(-1) : []; }],
    title: () => t("文字稿跟着变"),
    body: () => t("「呃」回来了，删除线也没了。文字稿里任何删除线，点一下也能恢复。") },
  { id: "lnear", ch: 3, mode: "listen", side: "left", target: [".side-tabs", ".side-near"],
    clicks: ['[data-testid="tab-near"]'], done: () => true,
    title: () => t("这附近改了什么"),
    body: () => t("点右边的 **这附近改了什么** 标签：播放头附近的改动都列在这里，可以直接 **恢复** 或 **重新应用**。刚才恢复的「呃」也在这里。"),
    hint: () => t("点开标签后继续") },

  // 4 对 LACUNA 说
  { id: "ctx", ch: 4, mode: "listen", side: "top",
    enter: (c) => {
      click('[data-testid="tab-ai"]');
      if (c.marks?.actor) c.player.seek(c.marks.actor[0]);
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
  { id: "ctools", ch: 4, mode: "listen", side: "left", target: ['[data-testid="mic"]', "form.chat-form .btn-outline"],
    title: () => t("也可以用嘴说"),
    body: () => t("点 🎤 直接说话，不用打字。**记住** 是让 LACUNA 把这句当成以后的规则（比如「笑声别剪」），下一集也照做。") },
  { id: "csend", ch: 4, mode: "listen", side: "left", target: ["form.chat-form button.btn-primary"],
    enter: () => {
      const el = q("form.chat-form textarea") as HTMLTextAreaElement | null;
      if (el && !el.value.trim()) fill("form.chat-form textarea", TOUR_CHAT());
    },
    done: (c) => c.ep.proposals.length > 0,
    title: () => t("发送"),
    body: () => t("点 **发送**，看 LACUNA 怎么回答。"),
    hint: () => t("发送后继续") },
  { id: "cpend", ch: 4, mode: "listen", side: "bottom", target: ['[data-testid="edit-lanes"]'],
    enter: (c) => {
      const p = c.ep.proposals[0]?.edit;
      if (p) c.player.seek(Math.max(0, p.t - 3));
    },
    title: () => t("黄色虚线框：待批准"),
    body: () => t("LACUNA 不会直接改。它要删的地方先在时间线上用黄色虚线框标出来，等你点头。") },
  { id: "cab", ch: 4, mode: "listen", side: "left", target: ['[data-testid="proposal"]'],
    clicks: ['[data-testid="proposal"] .ab button:nth-of-type(1)', '[data-testid="proposal"] .ab button:nth-of-type(2)'], done: () => true,
    title: () => t("先听，再批准"),
    body: () => t("点 **试听前后对比**，再分别点 **▶ 现在** 和 **▶ 改后** 听一下。"),
    hint: () => t("两个都听过后继续") },
  { id: "cok", ch: 4, mode: "listen", side: "left", target: ['[data-testid="proposal"]', ".pstate.ok"],
    done: () => !q('[data-testid="proposal"]') && !!q(".pstate.ok"),
    title: () => t("满意就批准"),
    body: () => t("点 **批准**，这两句就删掉了。不满意的话，平时可以点「再改」接着说。"),
    hint: () => t("批准后继续") },

  // 5 手动删除
  { id: "dlanes", ch: 5, mode: "listen", side: "bottom", target: [".ml .ml-body"],
    enter: (c) => {
      if (c.marks?.water) c.player.seek(Math.max(0, c.marks.water[0] - 3));
    },
    box: (c) => (c.marks?.water ? { track: c.marks.hosts[0], a: c.marks.water[0], b: c.marks.water[1] } : null),
    done: (c) => selOver(c.marks?.water),
    title: () => t("自己动手删一段"),
    body: (h) => t("{a}说「等一下，我喝口水」，这句不要。在{a}的轨道上 **按住鼠标**，从橙色虚线框左边拖到右边。", h),
    hint: () => t("拖选后继续") },
  { id: "dbar", ch: 5, mode: "listen", side: "bottom", target: ['[data-testid="ml-menu"]', '[data-testid="ml-sel"]'],
    title: () => t("选中后的菜单"),
    body: () => t("松开鼠标，选区旁边弹出菜单：**删掉这段**（Ctrl X），或者 **只静音** 其中一个人。空格只放选中的这段，Esc 取消选中；拖选区的边可以调整范围。") },
  { id: "dcut", ch: 5, mode: "listen", side: "bottom", target: ['[data-testid="ml-menu"]', '[data-testid="ml-sel"]'],
    init: (c) => (c.memo.n = manual(c.ep, false)),
    done: (c) => manual(c.ep, false) > Number(c.memo.n ?? 0),
    title: () => t("删掉这段"),
    body: () => t("点菜单里的 **删掉这段**。"),
    hint: () => t("删掉后继续") },
  { id: "dtx", ch: 5, mode: "listen", side: "top", target: ['[data-testid="transcript-edit"]'],
    title: () => t("在文字稿里删，更快"),
    body: () => t("不想在波形上找，就在文字稿里 **选中文字**（可以只选一个词），下面会出现工具条：**删掉这段**、**只静音** 某人、**▶ 听选中**、**取消**。删过的字显示删除线，点一下就恢复。") },
  { id: "dhelp", ch: 5, mode: "listen", side: "right", free: true, target: ['[data-testid="ml-help"]', ".ml-help-tip"],
    enter: () => (q('[data-testid="ml-help"]') as HTMLElement | null)?.focus(),
    title: () => t("忘了怎么操作？"),
    body: () => t("时间线标题旁的 **?** 里是所有鼠标和键盘操作：放大缩小（Ctrl + 滚轮）、左右移动、撤销（Ctrl + Z）……以后把鼠标移到 **?** 上就能看到。") },

  // 6 手动静音
  { id: "mlanes", ch: 6, mode: "listen", side: "bottom", target: [".ml .ml-body"],
    enter: (c) => {
      if (c.marks?.cough) c.player.seek(Math.max(0, c.marks.cough[0] - 3));
    },
    box: (c) => (c.marks?.cough ? { track: c.marks.hosts[0], a: c.marks.cough[0] - 0.1, b: c.marks.cough[1] + 0.1 } : null),
    done: (c) => selOver(c.marks?.cough),
    title: (h) => t("{b}说话时，{a}咳了一声", h),
    body: (h) => t("删掉整段会把{b}的话也删了。先在{a}的轨道上拖选咳嗽那一小段（橙色虚线框）。", h),
    hint: () => t("拖选后继续") },
  { id: "mmute", ch: 6, mode: "listen", side: "bottom", target: ['[data-testid="ml-menu"]', '[data-testid="ml-sel"]'],
    init: (c) => (c.memo.n = manual(c.ep, true)),
    done: (c) => manual(c.ep, true) > Number(c.memo.n ?? 0),
    title: () => t("只静音一个人"),
    body: (h) => t("点 **只静音 {a}**：{b}的话留着，只把{a}那条轨道的这一下变安静。", h),
    hint: () => t("静音后继续") },
  { id: "mtoast", ch: 6, mode: "listen", side: "top", target: [".toast"],
    title: () => t("做错了也不怕"),
    body: () => t("每次改动后下面都会出现提示；按 **Ctrl + Z** 就撤销刚才那一下。所有改动都不碰原始录音。") },
  { id: "mstripe", ch: 6, mode: "listen", side: "bottom",
    box: (c) => (c.marks?.cough ? { track: c.marks.hosts[0], a: c.marks.cough[0] - 0.3, b: c.marks.cough[1] + 0.3 } : null),
    target: [(c) => [...document.querySelectorAll(`[data-testid="lane-${c.marks?.hosts[0] ?? c.ep.tracks[0]?.name}"]`)]],
    title: () => t("斜线 = 只删了一个人"),
    body: (h) => t("{a}的轨道上出现斜线，表示这里只静音了{a}。把鼠标移上去也能恢复。", h) },
  { id: "mnext", ch: 6, mode: "listen", side: "bottom", target: ['[data-testid="next-step"]'], done: isMode("levels"),
    title: () => t("剪辑做完了"),
    body: () => t("点 **下一步：声音**，把两人的音量调一致。"),
    hint: () => t("点「下一步」") },

  // 7 声音
  { id: "vauto", ch: 7, mode: "levels", side: "bottom", target: ['[data-tour="levels-auto"]'],
    clicks: ['[data-tour="levels-auto"]'], done: () => !q('[data-tour="levels-auto"][disabled]'),
    title: () => t("一个大声，一个小声"),
    body: (h) => t("{a}离麦克风近，比{b}响很多。点 **统一两人音量**，LACUNA 把两人都调到同一个响度。", h),
    hint: () => t("点击后继续") },
  { id: "vmeter", ch: 7, mode: "levels", side: "bottom", target: [".levels-tracks .levels-top"],
    title: () => t("看这把尺子"),
    body: () => t("白线是原始音量，彩色条是现在，绿线是目标。统一后两人的彩色条都到了绿线，右边的波形也一样高了。") },
  { id: "vctl", ch: 7, mode: "levels", side: "right", free: true, target: ['[data-tour="levels-controls"]'],
    title: () => t("还想调，也可以"),
    body: () => t("拖滑块、点 **−1 / +1** 或点 **用建议值**。太响时会提示「最响的地方会被轻轻压住」。不调也没关系，这一步只是告诉你可以调。") },
  { id: "vclip", ch: 7, mode: "levels", side: "right", target: ['[data-tour="levels-clip"]'],
    title: () => t("破音"),
    body: () => t("LACUNA 会找出破音并自动修复。修不了的会列在这里，点时间就从前 2 秒开始听。示例里没有破音。") },
  { id: "vlisten", ch: 7, mode: "levels", side: "top", free: true, target: ['[data-tour="levels-listen"]'],
    title: () => t("对比着听"),
    body: () => t("播放时点 **对比这里：原始 / 调整后**，听统一前后的差别。") },
  { id: "vnext", ch: 7, mode: "levels", side: "bottom", target: ['[data-testid="next-step"]'], done: isMode("music"),
    title: () => t("声音好了"),
    body: () => t("点 **下一步：配乐**。"),
    hint: () => t("点「下一步」") },

  // 8 配乐
  { id: "ulib", ch: 8, mode: "music", side: "right", free: true, target: ['[data-tour="music-library"]'],
    title: () => t("左边是素材库"),
    body: () => t("示例准备了 3 首 CC0 授权的音乐。点 **▶** 能先试听。平时点上面的上传按钮，加你自己的。") },
  { id: "uintro", ch: 8, mode: "music", side: "right", target: ['[data-tour="music-asset-intro"]', ".mlib-menu"],
    done: () => !!q(intro),
    title: () => t("放上片头"),
    body: () => t("点第一首的 **放到 ▾**，选 **片头**。"),
    hint: () => t("选好后继续") },
  { id: "ucard", ch: 8, mode: "music", side: "left", target: [intro],
    title: () => t("片头放好了"),
    body: () => t("右边多了一张「片头」卡片：歌名、在成品里的时间、试听、改类型、去掉。") },
  { id: "uoutro", ch: 8, mode: "music", side: "right", target: ['[data-tour="music-asset-outro"]', ".mlib-menu"],
    done: () => !!q('[data-testid="placement"][data-role="outro"]'),
    title: () => t("再放片尾"),
    body: () => t("点第二首的 **放到 ▾**，选 **片尾**。"),
    hint: () => t("选好后继续") },
  { id: "ucurve", ch: 8, mode: "music", side: "left", target: [`${intro} [data-testid="music-curve"]`],
    enter: openIntro,
    title: () => t("这条线是音乐的音量"),
    body: () => t("点开片头卡片，就能看到：淡入 → 开头只放音乐 → 有人开口时自动压低 → 最后淡出。底下的色块是有人说话的地方。") },
  { id: "udot", ch: 8, mode: "music", side: "left", alsoOk: true, target: [`${intro} [data-testid="music-curve"]`],
    init: (c) => (c.memo.low = q(`${intro} [data-testid="curve-dot-low"]`)?.textContent ?? ""),
    enter: (c) => {
      openIntro();
      if (!c.memo.low) c.memo.low = q(`${intro} [data-testid="curve-dot-low"]`)?.textContent ?? "";
    },
    done: (c) => {
      const now = q(`${intro} [data-testid="curve-dot-low"]`)?.textContent ?? "";
      return !!c.memo.low && now !== c.memo.low;
    },
    title: () => t("拖白点，调音乐"),
    body: () => t("觉得说话时音乐还是有点吵？把「说话时压低」那个白点 **往下拖**。四个白点都能拖：左右改时间，上下改音量；也可以点一下白点再按方向键。"),
    hint: () => t("拖一下白点后继续") },
  { id: "uslide", ch: 8, mode: "music", side: "top", free: true, target: [`${intro} [data-tour="music-sliders"]`],
    title: () => t("不想拖，也能调数值"),
    body: () => t("每个白点都有对应的滑块；数字可以直接输入后按回车，**− / +** 每次调一格。刚才拖的白点，就是这里的「说话时压低」。") },
  { id: "umore", ch: 8, mode: "music", side: "top", free: true, target: [`${intro} [data-testid="music-more-panel"]`],
    enter: () => {
      openIntro();
      if (!q(`${intro} [data-testid="music-more-panel"]`)) click(`${intro} [data-testid="music-more"]`);
    },
    title: () => t("更多设置"),
    body: () => t("「歌从 / 裁到」选用歌的哪一段；「位置」可以早 1 秒、晚 1 秒、±5 秒；还有各段淡入淡出的用时。") },
  { id: "utry", ch: 8, mode: "music", side: "bottom", target: [`${intro} [data-tour="music-try"]`],
    clicks: [`${intro} [data-tour="music-try"]`], done: () => true,
    title: () => t("试听这一处"),
    body: () => t("改完点 **试听这一处**，只听片头这一小段。"),
    hint: () => t("试听后继续") },
  { id: "ufinal", ch: 8, mode: "music", side: "bottom", free: true, target: ['[data-tour="music-final"]'],
    title: () => t("听整集成品"),
    body: () => t("这里放的是加了配乐的成品，导出的就是这一版。") },
  { id: "usend", ch: 8, mode: "music", side: "top", target: ['[data-tour="music-assist"]'],
    enter: () => window.setTimeout(() => fill('[data-tour="music-assist"] textarea', TOUR_MUSIC()), 50),
    done: () => !!q('[data-testid="music-draft"]'),
    title: () => t("说一句，让 LACUNA 调"),
    body: () => t("不想自己调数值，也可以直接说。句子已经填好：「{text}」，点 **发送**。", { text: TOUR_MUSIC() }),
    hint: () => t("发送后继续") },
  { id: "uadopt", ch: 8, mode: "music", side: "bottom", target: ['[data-testid="music-draft"]'],
    clicks: ['[data-testid="music-draft"] .btn-primary'], done: () => !q('[data-testid="music-draft"]'),
    title: () => t("采用，还是不要"),
    body: () => t("LACUNA 的改动先变成建议，可以点 **试听**。满意就点 **采用**，片头卡片上的曲线会跟着变；不满意就点「不要」。"),
    hint: () => t("采用后继续") },
  { id: "udefault", ch: 8, mode: "music", side: "bottom", free: true, target: ['[data-tour="music-toolbar"]'],
    title: () => t("下一集不用再放一遍"),
    body: () => t("点 **设为默认片头片尾**，以后每一集都会自动放好同样的片头片尾和设置。旁边的「用在」可以选只这一集、本专辑或整个节目。") },
  { id: "ucredit", ch: 8, mode: "music", side: "top", target: ['[data-tour="music-credits"]'],
    title: () => t("BGM 署名"),
    body: () => t("用了谁的音乐，这里自动写好，发布时会放进节目简介。") },
  { id: "unext", ch: 8, mode: "music", side: "bottom", target: ['[data-testid="next-step"]'], done: isMode("export"),
    title: () => t("配乐好了"),
    body: () => t("点 **下一步：导出**。"),
    hint: () => t("点「下一步」") },

  // 9 导出
  { id: "xfmt", ch: 9, mode: "export", side: "bottom", free: true, target: ['[data-tour="export-formats"]'],
    title: () => t("选格式"),
    body: () => t("**MP3** 体积小，适合分享；**WAV** 音质最好，上传平台用。可以都选。") },
  { id: "xstart", ch: 9, mode: "export", side: "bottom", target: ['[data-tour="export-start"]', ".xmain .job"],
    done: () => !!q('[data-testid="export-result"]'),
    title: () => t("开始导出"),
    body: () => t("点 **开始导出**，几秒就好。"),
    hint: () => t("导出完继续") },
  { id: "xdl", ch: 9, mode: "export", side: "bottom", target: ['[data-tour="export-download"]'],
    clicks: ['[data-tour="export-download"] a[download]'], done: () => true,
    title: () => t("下载成品"),
    body: () => t("点 **下载**，这一集就做完了。"),
    hint: () => t("下载后继续") },
  { id: "xsum", ch: 9, mode: "export", side: "left", target: ['[data-tour="export-summary"]'],
    title: () => t("这一集的结果"),
    body: () => t("右边是这一集的结果：原始多长、成品多长、剪掉多少、配乐几处、两人音量是否已统一。") },
  { id: "xstd", ch: 9, mode: "export", side: "left", target: ['[data-tour="export-standard"]'],
    title: () => t("符合播客平台标准"),
    body: () => t("响度统一到 −16 LUFS，真峰值不超过 −1 dBTP，这是 Apple Podcasts、Spotify 等平台的标准，可以直接上传。") },
  { id: "xpub", ch: 9, mode: "export", side: "top", target: ['[data-tour="export-publish"]'],
    title: () => t("还有「发布」"),
    body: () => t("下一步「发布」里，LACUNA 会写标题、简介、show notes 和章节，还能做海报。示例就到这里，最后听一下前后对比。") },
];

export const DONE = "done";
