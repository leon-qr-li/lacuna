import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { EditInfo, Episode } from "../../api";
import type { Player } from "../../usePlayer";
import { t } from "../../i18n";
import { manualApi, TILE_S } from "./api";
import type { WaveTile } from "./api";
import { range, useChunks } from "./chunks";
import { SelBar } from "./SelBar";
import { MIN_SEL } from "./useManual";
import type { Manual } from "./useManual";
import "./manual.css";

const ZOOM_KEY = "lacuna.manual.span";
const MIN_SPAN = 3; // seconds across the lanes at the closest zoom ...
const MAX_SPAN = 600; // ... and the widest
const EDGE_PX = 7; // grab a selection edge within this many pixels
const TICK_STEPS = [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300]; // ruler label spacing: the first that leaves room

const clampSpan = (s: number) => Math.max(MIN_SPAN, Math.min(MAX_SPAN, s));
const readSpan = (): number => {
  try {
    const z = Number(localStorage.getItem(ZOOM_KEY));
    return z ? clampSpan(z) : 30;
  } catch {
    return 30;
  }
};
/** m:ss on the ruler, with tenths when labels are less than a second apart */
const tick = (s: number, step: number) => {
  const m = Math.floor(s / 60);
  const r = s - m * 60;
  return step < 1 ? `${m}:${r.toFixed(1).padStart(4, "0")}` : `${m}:${String(Math.round(r)).padStart(2, "0")}`;
};

/** One host's waveform for the visible window, drawn on a canvas in that host's colour. */
function Wave({ index, name, tiles, t0, span }: { index: number; name: string; tiles: Map<number, WaveTile>; t0: number; span: number }) {
  const ref = useRef<HTMLCanvasElement | null>(null);
  const [width, setWidth] = useState(0);
  const [theme, setTheme] = useState(0);
  useLayoutEffect(() => {
    const c = ref.current;
    if (!c) return;
    const ro = new ResizeObserver(() => setWidth(c.clientWidth));
    ro.observe(c);
    setWidth(c.clientWidth);
    const mo = new MutationObserver(() => setTheme((n) => n + 1)); // light / dark switch repaints
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "style"] });
    return () => {
      ro.disconnect();
      mo.disconnect();
    };
  }, []);
  useEffect(() => {
    const c = ref.current;
    if (!c || !width) return;
    const dpr = window.devicePixelRatio || 1;
    const h = c.clientHeight;
    c.width = Math.round(width * dpr);
    c.height = Math.round(h * dpr);
    const g = c.getContext("2d");
    if (!g) return;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, width, h);
    const css = getComputedStyle(c);
    g.fillStyle = css.getPropertyValue(`--host-${index % 6}`).trim() || css.color;
    const step = 2; // css px per bar
    for (let x = 0; x < width; x += step) {
      const a = t0 + (x / width) * span;
      const b = t0 + ((x + step) / width) * span;
      let v = -1;
      for (let k = Math.floor(a / TILE_S); k <= Math.floor(b / TILE_S); k++) {
        const tile = tiles.get(k);
        const pk = tile?.tracks.find((tr) => tr.name === name)?.peaks;
        if (!tile || !pk) continue;
        const i0 = Math.max(0, Math.floor((a - tile.start) * tile.per_s));
        const i1 = Math.min(pk.length, Math.max(i0 + 1, Math.ceil((b - tile.start) * tile.per_s)));
        for (let i = i0; i < i1; i++) v = Math.max(v, pk[i]);
      }
      if (v < 0) continue;
      const bh = Math.max(1, (v / 100) * (h - 8));
      g.fillRect(x, (h - bh) / 2, step - 0.6, bh);
    }
  }, [tiles, t0, span, width, index, name, theme]);
  return <canvas ref={ref} className="ml-wave" aria-hidden />;
}

/** The "?" next to the title: how to work the timeline, on hover or keyboard focus (Leon 2026-10-20). */
function Help() {
  const rows: [string, string][] = [
    [t("点一下"), t("播放头移到那里，时间线不动")],
    [t("在轨道上拖"), t("选一段；拖选区的边可以调整，Esc 取消")],
    [t("选中以后"), t("删掉这段（Del 键）、只静音某个人，或按播放只听选中的这一段")],
    [t("Ctrl + 滚轮"), t("以鼠标位置为中心放大、缩小")],
    [t("挪时间线"), t("拖上面的时间刻度条，或按住空格拖轨道，或直接滚轮")],
    [t("播放时"), t("播放头走到右边，时间线自动翻到下一页")],
  ];
  return (
    <span className="ml-help">
      <button type="button" className="ml-help-btn" aria-label={t("怎么用剪辑时间线")} aria-describedby="ml-help-tip" data-testid="ml-help">
        ?
      </button>
      <span className="ml-help-tip" role="tooltip" id="ml-help-tip">
        <b>{t("自己动手剪")}</b>
        <span className="ml-help-rows">
          {rows.map(([k, v]) => (
            <span key={k} className="ml-help-row">
              <span className="ml-help-k">{k}</span>
              <span>{v}</span>
            </span>
          ))}
        </span>
        <b>{t("AI 剪的和你剪的")}</b>
        <span className="ml-help-p">
          {t("橙色竖线是剪切点，斜纹是只删了一个人的地方，紫框是恢复过的，虚线框是 AI 提议、还在等你批准的。")}
        </span>
        <span className="ml-help-p">
          {t("AI 初剪、对话里让 AI 改的、你自己剪的，都是一样的改动：Ctrl + Z 撤销，或者在「这附近改了什么」里点恢复；AI 的提议在「审阅改动」或右边对话里批准。")}
        </span>
      </span>
    </span>
  );
}

/**
 * The timeline of 整集试听 with manual editing: each host's real waveform, smooth zoom, pan, and drag to select a
 * stretch (decision manual-editing). The selection is shared with the transcript card (TranscriptEdit).
 */
export function EditLanes({
  ep,
  time,
  player,
  highlight,
  m,
}: {
  ep: Episode;
  time: number;
  player: Player;
  highlight?: EditInfo | null;
  m: Manual;
}) {
  const { sel, setSel } = m;
  const d = ep.duration;
  // The window stays where it is: a click only moves the playhead (Leon 2026-10-20, "我不要居中"). It moves when
  // the user pans (drag the ruler, Space + drag or middle-drag on a lane, the wheel), zooms (Ctrl + wheel, around
  // the pointer), when playback runs off the right edge (it turns a page), or when a jump lands outside it.
  const [span, setSpan] = useState(readSpan);
  const [t0, setT0] = useState(() => Math.max(0, Math.min(time - span / 2, d - span)));
  const view = useRef({ t0, span, d });
  view.current = { t0, span, d };
  const place = (start: number, s = view.current.span) => {
    const ns = Math.min(clampSpan(s), Math.max(MIN_SPAN, view.current.d));
    setSpan(ns);
    setT0(Math.max(0, Math.min(start, view.current.d - ns)));
  };
  type Drag = { kind: "sel"; x0: number; anchor: number; moved: boolean; r: DOMRect } | { kind: "pan"; x0: number; t0: number; w: number };
  const drag = useRef<Drag | null>(null);
  const card = useRef<HTMLElement | null>(null);
  const hover = useRef(false);
  const space = useRef<{ panned: boolean } | null>(null);
  const [hand, setHand] = useState(false); // Space held over the timeline: the lanes pan instead of select
  const t1 = t0 + span;

  // follow the playhead only when it leaves the window by itself: playing past the right edge turns a page, and a
  // jump from elsewhere (transcript, review, ±5 s) that lands outside shows it; a pan away while paused stays
  const prevTime = useRef(time);
  useEffect(() => {
    const prev = prevTime.current;
    prevTime.current = time;
    if (drag.current) return;
    const { t0: a, span: s } = view.current;
    const inside = (v: number) => v >= a && v <= a + s;
    if (inside(time)) return;
    if (inside(prev) && time > a + s && time - prev < 1) place(time - s * 0.02);
    else if (Math.abs(time - prev) >= 0.5) place(time - s * 0.1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [time]);

  // Ctrl + wheel zooms around the pointer, a plain or Shift wheel pans, both over the ruler and lanes; Ctrl + wheel
  // anywhere on the card never zooms the page. React's onWheel is passive, so this listener is added by hand.
  useEffect(() => {
    const el = card.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      const area = (e.target as HTMLElement).closest<HTMLElement>(".ml-body, .ml-ruler");
      if (!area) {
        if (e.ctrlKey) e.preventDefault();
        return;
      }
      e.preventDefault();
      const r = area.getBoundingClientRect();
      const { t0: a, span: s } = view.current;
      const unit = e.deltaMode === 1 ? 33 : e.deltaMode === 2 ? r.width : 1; // lines / pages to pixels
      if (e.ctrlKey || e.metaKey) {
        const at = a + ((e.clientX - r.left) / r.width) * s;
        const ns = clampSpan(s * Math.exp(Math.max(-1, Math.min(1, (e.deltaY * unit) / 100)) * 0.2));
        place(at - ((at - a) / s) * ns, ns);
      } else {
        const dx = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
        place(a + ((dx * unit) / r.width) * s * 0.9);
      }
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Space held while the pointer is over the timeline turns the lanes into a hand; a tap without a drag still
  // plays / pauses like the global Space key, which keeps its meaning everywhere else.
  useEffect(() => {
    const typing = (e: KeyboardEvent) => ["INPUT", "TEXTAREA", "SELECT"].includes((e.target as HTMLElement).tagName);
    const down = (e: KeyboardEvent) => {
      if (e.code !== "Space" || typing(e) || e.ctrlKey || e.metaKey || e.altKey) return;
      if (!hover.current && !space.current) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      if (!space.current) {
        space.current = { panned: false };
        setHand(true);
      }
    };
    const up = (e: KeyboardEvent) => {
      if (e.code !== "Space" || !space.current) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      const tap = !space.current.panned;
      space.current = null;
      setHand(false);
      if (tap) player.toggle();
    };
    window.addEventListener("keydown", down, true);
    window.addEventListener("keyup", up, true);
    return () => {
      window.removeEventListener("keydown", down, true);
      window.removeEventListener("keyup", up, true);
    };
  }, [player]);

  useEffect(() => {
    try {
      localStorage.setItem(ZOOM_KEY, String(Math.round(span * 10) / 10));
    } catch {
      /* storage unavailable */
    }
  }, [span]);

  const tiles = useChunks<WaveTile>(ep.version, range(Math.floor(t0 / TILE_S), Math.floor(Math.min(t1, d) / TILE_S)), (k) =>
    manualApi.wave(ep.id, ep.version, k),
  );

  const x = (s: number) => `${(100 * (s - t0)) / span}%`;
  const w = (a: number, b: number) => `${(100 * Math.max(0, Math.min(b, t1) - Math.max(a, t0))) / span}%`;
  const at = (clientX: number, r: DOMRect) => Math.max(0, Math.min(d, t0 + ((clientX - r.left) / r.width) * span));

  const panFrom = (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    drag.current = { kind: "pan", x0: e.clientX, t0, w: e.currentTarget.getBoundingClientRect().width };
    if (space.current) space.current.panned = true;
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const down = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button === 1 || (e.button === 0 && space.current)) return panFrom(e);
    if (e.button !== 0) return;
    const r = e.currentTarget.getBoundingClientRect();
    let anchor = at(e.clientX, r);
    let moved = false;
    if (sel) {
      const px = (s: number) => r.left + ((s - t0) / span) * r.width;
      if (Math.abs(e.clientX - px(sel.a)) <= EDGE_PX) [anchor, moved] = [sel.b, true];
      else if (Math.abs(e.clientX - px(sel.b)) <= EDGE_PX) [anchor, moved] = [sel.a, true];
    }
    drag.current = { kind: "sel", x0: e.clientX, anchor, moved, r };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const rulerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button === 0 || e.button === 1) panFrom(e);
  };
  const move = (e: React.PointerEvent<HTMLDivElement>) => {
    const g = drag.current;
    if (!g) return;
    if (g.kind === "pan") return place(g.t0 - ((e.clientX - g.x0) / g.w) * span);
    if (!g.moved && Math.abs(e.clientX - g.x0) < 4) return;
    g.moved = true;
    const s = at(e.clientX, g.r);
    setSel({ a: Math.min(g.anchor, s), b: Math.max(g.anchor, s), from: "lanes" });
  };
  const up = (e: React.PointerEvent<HTMLDivElement>) => {
    const g = drag.current;
    drag.current = null;
    if (!g || g.kind === "pan") return;
    if (!g.moved) {
      setSel(null);
      player.seek(at(e.clientX, g.r)); // the window stays put
    } else setSel((s) => (s && s.b - s.a >= MIN_SEL ? s : null));
  };

  const visible = ep.edits.filter((e) => e.category !== "loudness" && e.t + e.len >= t0 && e.t <= t1);
  const step = TICK_STEPS.find((s) => s / span >= 0.12) ?? 300; // about 8 labels across
  const ticks = range(Math.ceil(t0 / step), Math.floor(t1 / step)).map((k) => k * step);
  const showSel = sel && sel.b > t0 && sel.a < t1;
  return (
    <section
      ref={card}
      className={`card lanes ml ${hand ? "is-hand" : ""}`}
      aria-label={t("剪辑时间线")}
      data-testid="edit-lanes"
      data-span={span.toFixed(1)}
      data-start={t0.toFixed(1)}
      onPointerEnter={() => (hover.current = true)}
      onPointerLeave={() => (hover.current = false)}
    >
      <div className="ml-head">
        <h2>{t("剪辑时间线")}</h2>
        <Help />
      </div>
      <div className="lane">
        <span className="lane-name" />
        <div className="ml-ruler mono" onPointerDown={rulerDown} onPointerMove={move} onPointerUp={up} onPointerCancel={up} role="presentation" data-testid="ml-ruler">
          {ticks.map((s) => (
            <span key={s} style={{ left: x(s) }}>
              {tick(s, step)}
            </span>
          ))}
        </div>
      </div>
      {ep.tracks.map((tr, i) => (
        <div className="lane" key={tr.name}>
          <span className="lane-name">{tr.name}</span>
          <div
            className="lane-body ml-body"
            onPointerDown={down}
            onPointerMove={move}
            onPointerUp={up}
            onPointerCancel={up}
            role="presentation"
            data-testid={`lane-${tr.name}`}
          >
            {!tiles.size &&
              tr.clips
                .filter(([a, b]) => b >= t0 && a <= t1)
                .map(([a, b]) => <div key={a} className={`clip clip-${i} ml-clip`} style={{ left: x(Math.max(a, t0)), width: w(a, b) }} />)}
            <Wave index={i} name={tr.name} tiles={tiles} t0={t0} span={span} />
            {visible.map((e) => {
              if (e.tracks && !e.tracks.includes(tr.name)) return null;
              if (e.status === "restored" || (e.tracks && e.status === "applied"))
                return <div key={e.id} className={`mark-span ${e.status}`} style={{ left: x(Math.max(e.t, t0)), width: w(e.t, e.t + e.len) }} title={e.title} />;
              return <div key={e.id} className="mark-cut" style={{ left: x(e.t) }} title={e.title} />;
            })}
            {highlight && highlight.t + highlight.len >= t0 && highlight.t <= t1 && (
              <div
                className="mark-pending"
                style={{ left: x(Math.max(highlight.t, t0)), width: w(highlight.t, highlight.t + Math.max(highlight.len, 0.3)) }}
                title={highlight.title}
              />
            )}
            {showSel && <div className="ml-sel" style={{ left: x(Math.max(sel.a, t0)), width: w(sel.a, sel.b) }} data-testid="ml-sel" />}
            {time >= t0 && time <= t1 && <div className="ml-head-line" style={{ left: x(time) }} />}
          </div>
        </div>
      ))}
      {sel?.from === "lanes" && <SelBar ep={ep} m={m} />}
      <p className="muted small legend">
        <span className="lg lg-cut" /> {t("剪切点")}　<span className="lg lg-lift" /> {t("单轨删减")}
        <span className="lg lg-restored" /> {t("已恢复")}　<span className="lg lg-pending" /> {t("待批准")}　<span className="lg ml-lg-sel" /> {t("你选中的")}
      </p>
    </section>
  );
}
