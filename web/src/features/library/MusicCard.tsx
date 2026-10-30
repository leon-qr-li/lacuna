// 配乐 design B: one card per piece of music. The selected card opens into its volume curve (four
// dots to drag), sliders with numbers for the three main values, and 更多设置 with every other number.
import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent as RKeyboardEvent, PointerEvent as RPointerEvent } from "react";
import type { Placement, PlacementPatch, Role } from "./api";
import { fmt, parseTime } from "../../api";
import { CREDIT_LABEL } from "./LibraryView";
import { t } from "../../i18n";

export const ANCHORED: Role[] = ["interlude", "bed", "clip"];
export const ROLES: Role[] = ["intro", "interlude", "outro", "bed", "clip"];
export const ROLE_NAME: Record<Role, string> = {
  intro: t("片头"),
  interlude: t("间奏 / 休息间隙"),
  outro: t("片尾"),
  bed: t("铺底"),
  clip: t("台词"),
};
export const ROLE_HELP: Record<Role, string> = {
  intro: t("整首从头放：先只有音乐，然后压低当背景，人声进来，歌在背景里放完"),
  interlude: t("对话停下，音乐升起来全音量放几秒，再压低当背景，对话接着来，歌放完为止"),
  outro: t("先压低垫在最后的对话下，说完拜拜升起来，放到结尾淡出"),
  bed: t("整段固定压低当背景。位置空着就由 LACUNA 放进没有其他配乐的空档；写了位置就从那里放"),
  clip: t("插入一段台词，前后各留一点空"),
};
const BG_DEFAULT = 22; // dB, new placements (lacuna_app/music.py BG_DB)
const BED_BG_DEFAULT = 25; // dB, a new bed (music.py BED_BG_DB)
const bgDefault = (r: Role) => (r === "bed" ? BED_BG_DEFAULT : BG_DEFAULT);
const RAMP_DEFAULT = 2; // s (music.py RAMP_S)

type Tune = "src_in_s" | "src_out_s" | "gain_db" | "solo_s" | "ramp_s" | "ramp_out_s" | "bg_db" | "pre_s" | "bye_s" | "fade_out_s";
type FieldDef = { k: Tune; label: string; time?: boolean; auto?: boolean };
// which numbers Leon sets for each use; times in the song accept 2:30 or 150
const FIELDS: Record<Role, FieldDef[]> = {
  intro: [
    { k: "solo_s", label: t("只放音乐（秒）") },
    { k: "bg_db", label: t("背景压低（dB）") },
    { k: "ramp_s", label: t("压低用时（秒）") },
  ],
  interlude: [
    { k: "ramp_s", label: t("淡入（秒）") },
    { k: "solo_s", label: t("全音量时长（秒）") },
    { k: "ramp_out_s", label: t("淡出到背景（秒）") },
    { k: "bg_db", label: t("背景压低（dB）") },
    { k: "pre_s", label: t("间隙前先垫（秒）") },
  ],
  outro: [
    { k: "bye_s", label: t("说拜拜在歌的"), time: true },
    { k: "ramp_s", label: t("升起用时（秒）") },
    { k: "bg_db", label: t("背景压低（dB）") },
    { k: "fade_out_s", label: t("结尾淡出（秒）"), auto: true },
  ],
  bed: [
    { k: "bg_db", label: t("背景压低（dB）") },
    { k: "fade_out_s", label: t("结尾淡出（秒）"), auto: true },
  ],
  clip: [],
};
const COMMON: FieldDef[] = [
  { k: "src_in_s", label: t("歌从"), time: true },
  { k: "src_out_s", label: t("裁到"), time: true },
];
const GAIN: FieldDef = { k: "gain_db", label: t("音量（dB）") };
/** the three values with a slider; the rest are under 更多设置 */
const SLID: Tune[] = ["gain_db", "bg_db", "solo_s"];

const show = (v: number | null | undefined, time?: boolean) => (v == null ? "" : time ? fmt(v) : String(v));
const r1 = (v: number) => Math.round(v * 10) / 10;
const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi);

/** One line in plain words: what Leon will hear for this piece of music. */
export function describe(p: Placement): string {
  const whole = p.asset_duration_s != null && p.src_out_s >= p.asset_duration_s - 0.05 && p.src_in_s < 0.05;
  const len = whole ? t("整首 {p0}", { p0: fmt(p.src_out_s - p.src_in_s) }) : t("歌的 {p0}–{p1}", { p0: fmt(p.src_in_s), p1: fmt(p.src_out_s) });
  const bg = p.bg_db ?? bgDefault(p.role);
  switch (p.role) {
    case "intro":
      return t("{len}：前 {solo} 秒只有音乐，再用 {ramp} 秒压低 {bg} dB，人声进来，歌在背景里放完", {
        len, solo: Math.min(p.solo_s ?? 0, p.src_out_s - p.src_in_s), ramp: p.ramp_s ?? 0, bg,
      });
    case "interlude":
      return t("{len}：对话停，{ramp} 秒淡入，全音量 {solo} 秒，再 {out} 秒压低 {bg} dB，对话接着来，歌在背景里放完", {
        len, solo: p.solo_s ?? 0, ramp: p.ramp_s ?? 0, out: p.ramp_out_s ?? p.ramp_s ?? 0, bg,
      });
    case "outro":
      return t("{len}：压低 {bg} dB 垫在对话下，你说拜拜时在歌的 {bye}，之后升起来，放到 {end} 结束", {
        len, bg, bye: fmt(p.bye_s ?? 0), end: fmt(p.src_out_s),
      });
    case "bed":
      return (
        (p.auto ? t("{len}：LACUNA 放在没有其他配乐的空档，整段压低 {bg} dB 当背景", { len, bg }) : t("{len}：整段压低 {bg} dB 当背景", { len, bg })) +
        (p.loop ? t("，循环填满这一段") : "")
      );
    default:
      return len;
  }
}

// ---------------------------------------------------------------------------------------------------
// the volume curve

const TOP_DB = 6;
const BOTTOM_DB = -40;
type Dot = {
  key: string;
  label: string;
  x: number; // seconds from the start of the piece
  db: number;
  /** a drag to (x, db) → the values it changes; null: that direction doesn't move */
  move: (x: number, db: number) => PlacementPatch;
  xs?: boolean; // left / right changes something
};
type Shape = { dots: Dot[]; path: [number, number][]; talk: [number, number][]; span: number };

function fadeOut(p: Placement): number {
  const trimmed = p.asset_duration_s != null && p.src_out_s < p.asset_duration_s - 0.05;
  return p.fade_out_s ?? (trimmed ? (p.role === "outro" ? 10 : 3) : 0);
}

/** Where the music is loud and where it sits under the talk, from the placement's numbers (music.py). */
export function shape(p: Placement): Shape | null {
  if (p.role === "clip") return null;
  const piece = p.end_s != null && p.start_s != null ? p.end_s - p.start_s : p.src_out_s - p.src_in_s;
  const span = Math.max(piece, 1);
  const hi = p.gain_db ?? 0;
  const bg = p.bg_db ?? bgDefault(p.role);
  const lo = hi - bg;
  const ramp = p.ramp_s ?? RAMP_DEFAULT;
  const fo = fadeOut(p);
  const end = clamp(span - fo, 0, span);
  const S = BOTTOM_DB - 10; // silence: below the floor
  const half = (v: number) => Math.round(v * 2) / 2;
  const y = (d: number) => half(clamp(d, -30, 12));
  const bgOf = (d: number) => half(clamp(hi - d, 0, 40));
  const fadeDot = (db: number, level: "hi" | "lo"): Dot => ({
    key: "out",
    label: t("淡出 {n} 秒", { n: r1(fo) }),
    x: end,
    db,
    xs: true,
    move: (x, d) => ({ fade_out_s: r1(clamp(span - x, 0, 30)), ...(level === "hi" ? { gain_db: y(d) } : { bg_db: bgOf(d) }) }),
  });
  switch (p.role) {
    case "intro": {
      const solo = Math.min(p.solo_s ?? 0, span);
      const fi = Math.min(0.5, span / 20);
      const down = Math.min(solo + ramp, span);
      return {
        span,
        talk: [[down, span]],
        path: [[0, S], [fi, hi], [solo, hi], [down, lo], [end, lo], [span, S]],
        dots: [
          { key: "in", label: t("淡入"), x: fi, db: hi, move: (_x, d) => ({ gain_db: y(d) }) },
          { key: "solo", label: t("只放音乐 {n} 秒", { n: r1(solo) }), x: solo, db: hi, xs: true, move: (x, d) => ({ solo_s: r1(clamp(x, 0, 600)), gain_db: y(d) }) },
          { key: "low", label: t("说话时压低 {n} dB", { n: r1(bg) }), x: down, db: lo, xs: true, move: (x, d) => ({ ramp_s: r1(clamp(x - solo, 0, 10)), bg_db: bgOf(d) }) },
          fadeDot(lo, "lo"),
        ],
      };
    }
    case "interlude": {
      const pre = p.pre_s ?? 0;
      const solo = p.solo_s ?? 0;
      const out = p.ramp_out_s ?? ramp;
      const up = pre + ramp;
      const full = up + solo;
      const down = Math.min(full + out, span);
      return {
        span,
        talk: [...(pre > 0 ? ([[0, pre]] as [number, number][]) : []), [down, span]],
        path: [...(pre > 0 ? ([[0, S], [0.01, lo], [pre, lo]] as [number, number][]) : [[0, S]] as [number, number][]), [up, hi], [full, hi], [down, lo], [end, lo], [span, S]],
        dots: [
          { key: "in", label: t("淡入 {n} 秒", { n: r1(ramp) }), x: up, db: hi, xs: true, move: (x, d) => ({ ramp_s: r1(clamp(x - pre, 0, 10)), gain_db: y(d) }) },
          { key: "solo", label: t("全音量 {n} 秒", { n: r1(solo) }), x: full, db: hi, xs: true, move: (x, d) => ({ solo_s: r1(clamp(x - up, 0, 600)), gain_db: y(d) }) },
          { key: "low", label: t("说话时压低 {n} dB", { n: r1(bg) }), x: down, db: lo, xs: true, move: (x, d) => ({ ramp_out_s: r1(clamp(x - full, 0, 10)), bg_db: bgOf(d) }) },
          fadeDot(lo, "lo"),
        ],
      };
    }
    case "outro": {
      const bye = clamp((p.bye_s ?? p.src_in_s) - p.src_in_s, 0, span);
      const fi = Math.min(1.5, bye);
      const rise = Math.min(bye + ramp, span);
      return {
        span,
        talk: [[0, bye]],
        path: [[0, S], [fi, lo], [bye, lo], [rise, hi], [end, hi], [span, S]],
        dots: [
          { key: "low", label: t("说话时压低 {n} dB", { n: r1(bg) }), x: fi, db: lo, move: (_x, d) => ({ bg_db: bgOf(d) }) },
          { key: "bye", label: t("说完拜拜"), x: bye, db: lo, xs: true, move: (x, d) => ({ bye_s: r1(clamp(p.src_in_s + x, p.src_in_s, p.src_out_s)), bg_db: bgOf(d) }) },
          { key: "rise", label: t("升起来 {n} 秒", { n: r1(ramp) }), x: rise, db: hi, xs: true, move: (x, d) => ({ ramp_s: r1(clamp(x - bye, 0, 10)), gain_db: y(d) }) },
          fadeDot(hi, "hi"),
        ],
      };
    }
    default: {
      // bed: one level all the way, under the talk
      const fi = Math.min(1.5, span / 4);
      return {
        span,
        talk: [[0, span]],
        path: [[0, S], [fi, lo], [end, lo], [span, S]],
        dots: [
          { key: "low", label: t("说话时压低 {n} dB", { n: r1(bg) }), x: fi, db: lo, move: (_x, d) => ({ bg_db: bgOf(d) }) },
          fadeDot(lo, "lo"),
        ],
      };
    }
  }
}

const px = (x: number, span: number) => (100 * clamp(x, 0, span)) / span;
const py = (db: number) => (100 * (TOP_DB - clamp(db, BOTTOM_DB, TOP_DB))) / (TOP_DB - BOTTOM_DB);

/** The small curve on a closed card. */
export function MiniCurve({ p }: { p: Placement }) {
  const s = shape(p);
  if (!s) return null;
  return (
    <svg className="mcurve-mini" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
      <polyline points={s.path.map(([x, d]) => `${px(x, s.span)},${py(d)}`).join(" ")} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

/** The volume curve with dots to drag: left / right changes a time, up / down a level. Arrow keys too. */
function Curve({ p, onCommit }: { p: Placement; onCommit: (patch: PlacementPatch) => void }) {
  const [draft, setDraft] = useState<PlacementPatch | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const drag = useRef<{ key: string; patch: PlacementPatch | null; x0: number; y0: number } | null>(null);
  useEffect(() => setDraft(null), [p]);
  const shown = draft ? ({ ...p, ...draft } as Placement) : p;
  const s = shape(shown);
  const base = shape(p);
  if (!s || !base) return null;
  const at = (e: RPointerEvent) => {
    const r = box.current!.getBoundingClientRect();
    const x = (clamp(e.clientX - r.left, 0, r.width) / Math.max(r.width, 1)) * base.span;
    const db = TOP_DB - (clamp(e.clientY - r.top, 0, r.height) / Math.max(r.height, 1)) * (TOP_DB - BOTTOM_DB);
    return [x, db] as const;
  };
  const dotOf = (key: string) => base.dots.find((d) => d.key === key)!;
  const onMove = (e: RPointerEvent) => {
    if (!drag.current) return;
    const d = dotOf(drag.current.key);
    const [x, db] = at(e);
    // a mostly vertical drag keeps the time, a mostly horizontal one the level
    const sideways = Math.abs(e.clientX - drag.current.x0) > 4;
    const updown = Math.abs(e.clientY - drag.current.y0) > 4;
    if (!sideways && !updown) return;
    const patch = d.move(d.xs && sideways ? x : d.x, updown ? db : d.db);
    drag.current.patch = patch;
    setDraft(patch);
  };
  const onUp = () => {
    const done = drag.current;
    drag.current = null;
    if (done?.patch) onCommit(done.patch);
  };
  const key = (d: Dot, e: RKeyboardEvent) => {
    const step: Record<string, [number, number]> = { ArrowLeft: [-0.5, 0], ArrowRight: [0.5, 0], ArrowUp: [0, 1], ArrowDown: [0, -1] };
    const m = step[e.key];
    if (!m || (m[0] && !d.xs)) return;
    e.preventDefault();
    onCommit(d.move(d.x + m[0], d.db + m[1]));
  };
  const pts = s.path.map(([x, d]) => `${px(x, s.span) * 10},${py(d) * 2}`).join(" ");
  return (
    <div className="mcurve" ref={box} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp} data-testid="music-curve" data-tour="music-curve">
      <svg viewBox="0 0 1000 200" preserveAspectRatio="none" aria-hidden="true">
        {s.talk.map(([a, b], i) => (
          <rect key={i} className="mcurve-talk" x={px(a, s.span) * 10} y={200 - 34} width={Math.max(px(b, s.span) - px(a, s.span), 0) * 10} height={34} />
        ))}
        <line className="mcurve-zero" x1="0" x2="1000" y1={py(0) * 2} y2={py(0) * 2} vectorEffect="non-scaling-stroke" />
        <polygon className="mcurve-fill" points={`0,200 ${pts} 1000,200`} />
        <polyline className="mcurve-line" points={pts} vectorEffect="non-scaling-stroke" />
      </svg>
      {s.talk.length > 0 && (
        <span className="mcurve-talk-label small" style={{ left: `${px(s.talk[s.talk.length - 1][0], s.span)}%` }}>
          {t("有人说话")}
        </span>
      )}
      {s.dots.map((d, i) => (
        <button
          key={d.key}
          type="button"
          className={[
            "mcurve-dot",
            drag.current?.key === d.key ? "is-drag" : "",
            px(d.x, s.span) > 75 ? "lab-right" : px(d.x, s.span) < 15 ? "lab-left" : "",
            // neighbours close together: every other label below its dot
            i > 0 && Math.abs(px(d.x, s.span) - px(s.dots[i - 1].x, s.span)) < 18 && i % 2 === 1 ? "lab-below" : "",
          ].join(" ")}
          data-testid={`curve-dot-${d.key}`}
          data-tour={`music-dot-${d.key}`}
          style={{ left: `${px(d.x, s.span)}%`, top: `${py(d.db)}%` }}
          aria-label={d.xs ? t("{label}（左右改时间，上下改音量）", { label: d.label }) : t("{label}（上下改音量）", { label: d.label })}
          onPointerDown={(e) => {
            e.preventDefault();
            (e.currentTarget.parentElement as HTMLElement).setPointerCapture(e.pointerId);
            drag.current = { key: d.key, patch: null, x0: e.clientX, y0: e.clientY };
          }}
          onKeyDown={(e) => key(dotOf(d.key), e)}
        >
          <span className="mcurve-dot-label small">{d.label}</span>
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------
// the card

function Slide({ label, aria, value, raw, min, max, step, unit, neg, onDraft, onCommit, onEnter }: {
  label: string;
  aria: string;
  value: number;
  raw: string;
  min: number;
  max: number;
  step: number;
  unit: string;
  neg?: boolean; // shown as "−22 dB": the input holds how much lower
  onDraft: (v: string) => void;
  onCommit: (v: number) => void;
  onEnter: () => void;
}) {
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const later = (v: number) => {
    onDraft(String(v));
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => onCommit(v), 450);
  };
  const now = (v: number) => {
    window.clearTimeout(timer.current);
    const c = Math.round(clamp(v, min, max) / step) * step;
    onDraft(String(r1(c)));
    onCommit(r1(c));
  };
  return (
    <div className="mslide">
      <div className="mslide-head">
        <span className="small muted">{label}</span>
        <span className="mslide-num">
          <button type="button" className="btn btn-small btn-ghost sq" aria-label={t("{label} 少一点", { label })} onClick={() => now(value - step)}>
            −
          </button>
          {neg && <span className="mono small">−</span>}
          <input className="num mono" inputMode="decimal" value={raw} aria-label={aria} onChange={(e) => onDraft(e.target.value)} onKeyDown={(e) => e.key === "Enter" && onEnter()} />
          <span className="small muted">{unit}</span>
          <button type="button" className="btn btn-small btn-ghost sq" aria-label={t("{label} 多一点", { label })} onClick={() => now(value + step)}>
            +
          </button>
        </span>
      </div>
      <input type="range" min={min} max={max} step={step} value={clamp(value, min, max)} aria-label={t("{label}滑块", { label })} onChange={(e) => later(Number(e.target.value))} />
    </div>
  );
}

export function PlacementCard({ p, open, more, taken, gapOpen, previewing, onOpen, onMore, onSave, onRemove, onPreview, onGap }: {
  p: Placement;
  open: boolean;
  more: boolean; // 更多设置 shown (kept for the page)
  taken: Role[]; // uses of the other placements (one intro, one outro)
  gapOpen: boolean; // a gap without music: 「放进间隙」 is offered
  onGap: () => Promise<boolean>;
  previewing: boolean;
  onOpen: () => void;
  onMore: (v: boolean) => void;
  onSave: (patch: PlacementPatch, done?: string) => Promise<boolean>;
  onRemove: () => void;
  onPreview: () => void;
}) {
  const fields = [...COMMON, ...FIELDS[p.role], GAIN];
  const fromP = () => Object.fromEntries(fields.map((f) => [f.k, show(p[f.k], f.time)])) as Record<Tune, string>;
  const key = fields.map((f) => p[f.k]).join("|");
  const [d, setD] = useState(fromP);
  const seen = useRef(fromP());
  useEffect(() => {
    // a save elsewhere on the card refreshes p: reset only the fields whose saved value changed, so a number
    // being typed in another field is kept
    const now = fromP();
    setD((x) => Object.fromEntries(fields.map((f) => [f.k, now[f.k] !== seen.current[f.k] ? now[f.k] : x[f.k]])) as Record<Tune, string>);
    seen.current = now;
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  const parsed = (f: FieldDef) => (f.time ? parseTime(d[f.k]) : d[f.k].trim() === "" ? null : Number(d[f.k]));
  const changed = fields.filter((f) => d[f.k] !== show(p[f.k], f.time));
  const bad = changed.some((f) => {
    const v = parsed(f);
    return (v == null && !f.auto) || (v != null && !isFinite(v));
  });
  const save = () => {
    if (!changed.length || bad) return;
    const patch: PlacementPatch = {};
    for (const f of changed) {
      const v = parsed(f);
      if (v != null) patch[f.k] = v;
    }
    void onSave(patch);
  };
  const [pos, setPos] = useState(p.at_s != null ? fmt(p.at_s) : "");
  useEffect(() => setPos(p.at_s != null ? fmt(p.at_s) : ""), [p.at_s]);
  const moveTo = (s: number | null) => s != null && void onSave({ at_s: Math.max(0, Math.round(s * 1000) / 1000) });
  const [until, setUntil] = useState(p.until_at_s != null ? fmt(p.until_at_s) : "");
  useEffect(() => setUntil(p.until_at_s != null ? fmt(p.until_at_s) : ""), [p.until_at_s]);
  const untilTo = () => {
    const v = parseTime(until);
    if (v != null && (p.until_at_s == null || Math.abs(v - p.until_at_s) >= 1)) void onSave({ until_s: v });
  };
  const num = (k: Tune, dflt: number) => {
    const v = Number(d[k]);
    return d[k]?.trim() !== "" && isFinite(v) ? v : (p[k] as number | null | undefined) ?? dflt;
  };
  const setOne = (k: Tune) => (v: number) => void onSave({ [k]: v } as PlacementPatch);
  const draft = (k: Tune) => (v: string) => setD((x) => ({ ...x, [k]: v }));
  // in a gap (features/gaps) the music plays inside the gap's length: no full-level time or background to set
  const soloField = p.in_gap ? undefined : FIELDS[p.role].find((f) => f.k === "solo_s");
  const hasBg = !p.in_gap && FIELDS[p.role].some((f) => f.k === "bg_db");
  const rest = fields.filter((f) => !SLID.includes(f.k));
  const anchored = ANCHORED.includes(p.role) && (p.at_s != null || p.role === "bed") && !p.missing;

  const actions = (
    <span className="row gap8 mcard-actions">
      {!p.missing && p.start_s != null && (
        <button type="button" className="btn btn-small btn-outline" onClick={onPreview} aria-pressed={previewing} data-tour="music-try">
          {previewing ? t("停止") : t("试听这一处")}
        </button>
      )}
      {!p.missing && (
        <select
          className={`chip-select role-select role-${p.role}`}
          value={p.in_gap ? "gap" : p.role}
          aria-label={t("改类型")}
          title={t("改类型：歌、裁剪和音量都保留")}
          onChange={(e) => {
            if (e.target.value === "gap") return void onGap();
            const role = e.target.value as Role;
            void onSave({ role }, t("已改成{role}", { role: ROLE_NAME[role] }));
          }}
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {r !== p.role && (r === "intro" || r === "outro") && taken.includes(r) ? t("{role}（替换现在的）", { role: ROLE_NAME[r] }) : ROLE_NAME[r]}
            </option>
          ))}
          {(p.in_gap || gapOpen) && (
            <option value="gap" disabled={!!p.in_gap}>
              {p.in_gap ? t("在间隙里") : t("放进间隙")}
            </option>
          )}
        </select>
      )}
      <button type="button" className="btn btn-small btn-outline" onClick={onRemove}>
        {t("去掉")}
      </button>
    </span>
  );

  return (
    <li className={`card mcard role-${p.role}${open ? " is-open" : ""}`} data-testid="placement" data-role={p.role} data-tour={`music-card-${p.role}`}>
      <div className="mcard-head">
        <button type="button" className="mcard-toggle" aria-expanded={open} onClick={onOpen} data-testid="placement-toggle">
          <span className={`chip role-chip role-${p.role}`}>{p.role_label}</span>
          <span className="mcard-title">
            <strong>{p.missing ? t("素材已不在库里") : p.asset_name}</strong>
            {p.start_s != null && (
              <span className="mono small muted">
                {t("成品 {a} – {b}", { a: fmt(p.start_s), b: fmt(p.end_s ?? 0) })}
                {p.inserted_s ? t(" · 插入 {p0} 秒", { p0: p.inserted_s.toFixed(1) }) : ""}
                {ANCHORED.includes(p.role) ? (p.auto ? t(" · 自动放进空档") : t(" · 已固定")) : ""}
              </span>
            )}
          </span>
          {!open && <MiniCurve p={p} />}
        </button>
        {actions}
      </div>
      {!p.missing && p.start_s != null && (
        <p className="small muted music-plan" data-testid="placement-plan">
          {p.in_gap ? t("放在 {s} 秒的间隙里：在间隙里淡入淡出，间隙长度不变。", { s: p.inserted_s ?? 0 }) : describe(p)}
        </p>
      )}
      {p.no_room && (
        <p className="small warn-line" data-testid="placement-no-room">
          {t("没有空档可放：别的配乐已经把时间占满了。可以写一个位置手动放，或者去掉别的配乐。")}
        </p>
      )}
      {open && !p.missing && (
        <>
          {p.in_gap ? null : p.role === "clip" ? (
            <p className="small muted">{t("台词插入对话里，前后各留 {n} 秒空。", { n: p.lead_s ?? 0.5 })}</p>
          ) : (
            <Curve p={p} onCommit={(patch) => void onSave(patch, t("已保存"))} />
          )}
          <div className="mslides" data-tour="music-sliders">
            <Slide
              label={t("音乐音量")}
              aria={GAIN.label}
              value={num("gain_db", 0)}
              raw={d.gain_db}
              min={-30}
              max={12}
              step={0.5}
              unit="dB"
              onDraft={draft("gain_db")}
              onCommit={setOne("gain_db")}
              onEnter={save}
            />
            {hasBg && (
              <Slide
                label={t("说话时压低")}
                aria={t("背景压低（dB）")}
                value={num("bg_db", bgDefault(p.role))}
                raw={d.bg_db}
                min={0}
                max={40}
                step={1}
                unit="dB"
                neg
                onDraft={draft("bg_db")}
                onCommit={setOne("bg_db")}
                onEnter={save}
              />
            )}
            {soloField && (
              <Slide
                label={p.role === "intro" ? t("只放音乐") : t("全音量时长")}
                aria={soloField.label}
                value={num("solo_s", 0)}
                raw={d.solo_s}
                min={0}
                max={Math.max(60, Math.ceil(p.src_out_s - p.src_in_s))}
                step={0.5}
                unit={t("秒")}
                onDraft={draft("solo_s")}
                onCommit={setOne("solo_s")}
                onEnter={save}
              />
            )}
          </div>
          {p.level_db != null && (
            <p className="small muted" data-testid="placement-level">
              {t("已自动调平 {db} dB，和人声相称；「音量（dB）」是在这之上的微调。", {
                db: `${p.level_db > 0 ? "+" : p.level_db < 0 ? "−" : "±"}${Math.abs(p.level_db).toFixed(1)}`,
              })}
            </p>
          )}
          <div className="row gap8 wrap mcard-foot">
            <button type="button" className="btn btn-small btn-ghost" aria-expanded={more} onClick={() => onMore(!more)} data-testid="music-more" data-tour="music-more">
              {more ? t("▾ 更多设置") : t("▸ 更多设置")}
            </button>
            <span className="grow" />
            {changed.length > 0 && <span className="small muted">{t("改了还没保存")}</span>}
            <button type="button" className="btn btn-small" disabled={!changed.length || bad} onClick={save}>
              {t("保存")}
            </button>
          </div>
          {more && (
            <div className="mmore" data-testid="music-more-panel">
              <div className="row gap12 wrap music-tune">
                {rest.map((f) => (
                  <label key={f.k} className="row gap8 small">
                    {f.label}
                    <input
                      className={f.time ? "time" : "num"}
                      inputMode="decimal"
                      value={d[f.k]}
                      placeholder={f.auto ? t("自动") : f.time ? "2:30" : ""}
                      onChange={(e) => setD({ ...d, [f.k]: e.target.value })}
                      onKeyDown={(e) => e.key === "Enter" && save()}
                      aria-label={f.label}
                    />
                  </label>
                ))}
              </div>
              {anchored && (
                <span className="row gap4 wrap small" data-testid="placement-position">
                  {t("位置")}
                  <input
                    className="time"
                    value={pos}
                    placeholder={p.auto ? t("自动") : ""}
                    onChange={(e) => setPos(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && moveTo(parseTime(pos))}
                    onBlur={() => parseTime(pos) !== null && (p.at_s == null || parseTime(pos) !== Math.floor(p.at_s)) && moveTo(parseTime(pos))}
                    aria-label={t("位置（成品时间）")}
                  />
                  {p.at_s != null && (
                    <>
                      <button type="button" className="btn btn-small btn-outline" onClick={() => moveTo(p.at_s! - 1)}>
                        {t("早 1 秒")}
                      </button>
                      <button type="button" className="btn btn-small btn-outline" onClick={() => moveTo(p.at_s! + 1)}>
                        {t("晚 1 秒")}
                      </button>
                      <button type="button" className="btn btn-small btn-outline" onClick={() => moveTo(p.at_s! - 5)}>
                        {t("−5 秒")}
                      </button>
                      <button type="button" className="btn btn-small btn-outline" onClick={() => moveTo(p.at_s! + 5)}>
                        {t("+5 秒")}
                      </button>
                    </>
                  )}
                  {p.role === "bed" && !p.auto && (
                    <>
                      {t("到")}
                      <input
                        className="time"
                        value={until}
                        placeholder={t("歌放完")}
                        onChange={(e) => setUntil(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && untilTo()}
                        onBlur={untilTo}
                        aria-label={t("铺到（成品时间）")}
                      />
                    </>
                  )}
                </span>
              )}
              {p.role === "bed" && (
                <div className="row gap12 wrap small" data-testid="bed-options">
                  <label className="check">
                    <input
                      type="checkbox"
                      checked={!!p.auto}
                      onChange={(e) =>
                        void onSave(
                          e.target.checked ? { auto: true } : { auto: false, at_s: p.at_s ?? 0 },
                          e.target.checked ? t("已改成自动放进空档") : t("已固定在现在的位置"),
                        )
                      }
                    />
                    {t("自动放进空档")}
                  </label>
                  <label className="check">
                    <input type="checkbox" checked={!!p.loop} onChange={(e) => void onSave({ loop: e.target.checked }, t("已保存"))} />
                    {t("循环填满")}
                  </label>
                </div>
              )}
            </div>
          )}
        </>
      )}
      <div className="row gap8 wrap small mcard-credit">
        <span>{t("BGM 署名：")}{p.credit_line}</span>
        {p.credit_status && <span className={`badge badge-${p.credit_status}`}>{CREDIT_LABEL[p.credit_status]}</span>}
      </div>
    </li>
  );
}
