import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { EditInfo, Episode } from "../../api";
import type { Player } from "../../usePlayer";
import { t } from "../../i18n";
import { manualApi, TILE_S } from "./api";
import type { WaveTile } from "./api";
import { range, useChunks } from "./chunks";
import { LaneMenu } from "./LaneMenu";
import { MIN_SEL } from "./useManual";
import type { Manual } from "./useManual";
import "./manual.css";

const ZOOM_KEY = "lacuna.manual.span";
const SHOW_EVENT = "lacuna:timeline-show";
/** Ask the 整集试听 timeline to show [a, b] (seconds on the timeline), zooming out if it doesn't fit. */
export const showOnTimeline = (a: number, b: number) => window.dispatchEvent(new CustomEvent(SHOW_EVENT, { detail: { a, b } }));
const MIN_SPAN = 3; // seconds across the lanes at the closest zoom ...
const MAX_SPAN = 600; // ... and the widest
const EDGE_PX = 7; // grab a selection edge within this many pixels
const POP_PX = 6; // an edit's card opens with the pointer this close to its mark
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

/** The "?" next to the title: what each action does, one line each (Leon 2026-10-20 wording). */
function Help() {
  const rows: [string, string][] = [
    [t("单击轨道"), t("播放头跳到那里，同时取消选中")],
    [t("按住鼠标拖动"), t("选一段")],
    [t("拖选区的边"), t("调整选区")],
    ["Ctrl + X", t("删掉选中的一段")],
    [t("空格"), t("播放 / 暂停（有选中时只放选中段）")],
    ["Esc", t("取消选中")],
    [t("Ctrl + 滚轮"), t("放大 / 缩小")],
    [t("拖刻度条，或按住空格拖"), t("左右移动时间线")],
    ["Ctrl + Z", t("撤销")],
  ];
  return (
    <span className="ml-help">
      <button type="button" className="ml-help-btn" aria-label={t("怎么用剪辑时间线")} aria-describedby="ml-help-tip" data-testid="ml-help">
        ?
      </button>
      <span className="ml-help-tip" role="tooltip" id="ml-help-tip">
        {rows.map(([k, v]) => (
          <span key={k} className="ml-help-row">
            <span className="ml-help-k">{k}</span>
            <span>{v}</span>
          </span>
        ))}
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
  top,
  bottom,
  popover,
}: {
  ep: Episode;
  time: number;
  player: Player;
  highlight?: EditInfo | null;
  m: Manual;
  /** shown under the title, above the ruler */
  top?: ReactNode;
  /** shown under the tracks (the player) */
  bottom?: ReactNode;
  /** a card for the edit under the pointer (listen / restore it from the timeline) */
  popover?: (e: EditInfo) => ReactNode;
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
  // showOnTimeline(a, b): bring that stretch into view (the tour points at spots that may be off-screen or
  // wider than a zoomed-in window)
  useEffect(() => {
    const on = (e: Event) => {
      const { a, b } = (e as CustomEvent<{ a: number; b: number }>).detail;
      const s = Math.max(view.current.span, (b - a) * 1.6 + 2);
      place(a - (Math.min(s, view.current.d) - (b - a)) / 2, s);
    };
    window.addEventListener(SHOW_EVENT, on);
    return () => window.removeEventListener(SHOW_EVENT, on);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  type Drag = { kind: "sel"; x0: number; anchor: number; moved: boolean; r: DOMRect } | { kind: "pan"; x0: number; t0: number; w: number };
  const drag = useRef<Drag | null>(null);
  const card = useRef<HTMLElement | null>(null);
  const hover = useRef(false);
  const space = useRef<{ panned: boolean } | null>(null);
  const [hand, setHand] = useState(false); // Space held over the timeline: the lanes pan instead of select
  const [edge, setEdge] = useState(false); // pointer on a selection edge (or dragging one): a resize cursor shows it
  const [pop, setPop] = useState<{ id: string; left: number; top: number } | null>(null); // the edit card under the pointer
  const popTimer = useRef(0);
  // the selection's menu: opens when a drag on the tracks ends (or on a right-click in the selection); Esc, a
  // click elsewhere or a new click on the tracks close it. Placed at the selection's right edge, between the tracks.
  const [menuOpen, setMenuOpen] = useState(false);
  const menu = useRef<HTMLDivElement | null>(null);
  const [menuAt, setMenuAt] = useState<{ left: number; top: number } | null>(null);
  const keepPop = () => window.clearTimeout(popTimer.current);
  const dropPop = (ms = 250) => {
    window.clearTimeout(popTimer.current);
    popTimer.current = window.setTimeout(() => setPop(null), ms);
  };
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
  /** "a" / "b" when clientX is on that edge of the selection */
  const onEdge = (clientX: number, r: DOMRect): "a" | "b" | null => {
    if (!sel) return null;
    const px = (s: number) => r.left + ((s - t0) / span) * r.width;
    if (Math.abs(clientX - px(sel.a)) <= EDGE_PX) return "a";
    if (Math.abs(clientX - px(sel.b)) <= EDGE_PX) return "b";
    return null;
  };
  const down = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button === 1 || (e.button === 0 && space.current)) return panFrom(e);
    if (e.button !== 0) return;
    const r = e.currentTarget.getBoundingClientRect();
    let anchor = at(e.clientX, r);
    let moved = false;
    const side = onEdge(e.clientX, r);
    if (sel && side) [anchor, moved] = [side === "a" ? sel.b : sel.a, true];
    drag.current = { kind: "sel", x0: e.clientX, anchor, moved, r };
    setPop(null);
    setMenuOpen(false);
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  /** the card for the edit within a few pixels of the pointer on this lane, below the lane */
  const hoverEdit = (e: React.PointerEvent<HTMLDivElement>, track: string) => {
    if (!popover || !card.current || space.current) return;
    const r = e.currentTarget.getBoundingClientRect();
    const px = (s: number) => r.left + ((s - t0) / span) * r.width;
    let best: { id: string; x: number; dist: number } | null = null;
    for (const ed of visible) {
      if (ed.tracks && !ed.tracks.includes(track)) continue;
      const a = px(Math.max(ed.t, t0));
      const b = ed.tracks || ed.status === "restored" ? px(Math.min(ed.t + ed.len, t1)) : a;
      const dist = e.clientX < a ? a - e.clientX : e.clientX > b ? e.clientX - b : 0;
      if (dist <= POP_PX && (!best || dist < best.dist)) best = { id: ed.id, x: Math.max(a, Math.min(e.clientX, b)), dist };
    }
    if (!best) return pop && dropPop();
    keepPop();
    const c = card.current.getBoundingClientRect();
    if (pop?.id !== best.id) setPop({ id: best.id, left: Math.max(150, Math.min(c.width - 150, best.x - c.left)), top: r.bottom - c.top + 6 });
  };
  const rulerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button === 0 || e.button === 1) panFrom(e);
  };
  const move = (e: React.PointerEvent<HTMLDivElement>) => {
    const g = drag.current;
    if (!g) {
      if (e.currentTarget.classList.contains("ml-body")) {
        setEdge(!space.current && !!onEdge(e.clientX, e.currentTarget.getBoundingClientRect()));
        hoverEdit(e, e.currentTarget.dataset.track ?? "");
      }
      return;
    }
    if (g.kind === "pan") return place(g.t0 - ((e.clientX - g.x0) / g.w) * span);
    if (!g.moved && Math.abs(e.clientX - g.x0) < 4) return;
    g.moved = true;
    const s = at(e.clientX, g.r);
    setSel({ a: Math.min(g.anchor, s), b: Math.max(g.anchor, s), from: "lanes" });
  };
  const up = (e: React.PointerEvent<HTMLDivElement>) => {
    const g = drag.current;
    drag.current = null;
    setEdge(false);
    if (!g || g.kind === "pan") return;
    if (!g.moved) {
      setSel(null);
      player.seek(at(e.clientX, g.r)); // the window stays put
    } else {
      setSel((s) => (s && s.b - s.a >= MIN_SEL ? s : null));
      setMenuOpen(true);
    }
  };
  /** right-click on the tracks: the selection's menu when the pointer is on the selection */
  const context = (e: React.MouseEvent<HTMLDivElement>) => {
    e.preventDefault();
    const r = e.currentTarget.getBoundingClientRect();
    const s = at(e.clientX, r);
    if (sel?.from === "lanes" && s >= sel.a - 0.05 && s <= sel.b + 0.05) setMenuOpen(true);
  };

  const lanesSel = sel?.from === "lanes" ? sel : null;
  useEffect(() => {
    if (!lanesSel) setMenuOpen(false);
  }, [lanesSel]);
  // Esc closes it (useManual drops the selection too); a click outside it closes it
  useEffect(() => {
    if (!menuOpen) return;
    const away = (e: PointerEvent) => !menu.current?.contains(e.target as Node) && setMenuOpen(false);
    const key = (e: KeyboardEvent) => e.key === "Escape" && setMenuOpen(false);
    window.addEventListener("pointerdown", away);
    window.addEventListener("keydown", key);
    return () => {
      window.removeEventListener("pointerdown", away);
      window.removeEventListener("keydown", key);
    };
  }, [menuOpen]);
  // where: 8 px right of the selection, vertically centred on the tracks; left of it when there is no room
  useLayoutEffect(() => {
    if (!menuOpen || !lanesSel || !card.current || !menu.current) return setMenuAt(null);
    const bodies = card.current.querySelectorAll<HTMLElement>(".ml-body");
    if (!bodies.length) return;
    const c = card.current.getBoundingClientRect();
    const first = bodies[0].getBoundingClientRect();
    const last = bodies[bodies.length - 1].getBoundingClientRect();
    const mw = menu.current.offsetWidth;
    const mh = menu.current.offsetHeight;
    const px = (v: number) => first.left - c.left + ((Math.max(t0, Math.min(t1, v)) - t0) / span) * first.width;
    let left = px(lanesSel.b) + 8;
    if (left + mw > c.width - 8) left = Math.max(8, px(lanesSel.a) - mw - 8);
    setMenuAt({ left, top: (first.top + last.bottom) / 2 - c.top - mh / 2 });
  }, [menuOpen, lanesSel, t0, t1, span]);

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
        <p className="muted small legend" data-testid="ml-legend">
          {([["lg-cut", t("剪切点")], ["lg-lift", t("单轨删减")], ["lg-restored", t("已恢复")], ["lg-pending", t("待批准")], ["ml-lg-sel", t("你选中的")]] as const).map(([c, label]) => (
            <span className="lg-item" key={c}>
              <span className={`lg ${c}`} />
              {label}
            </span>
          ))}
        </p>
      </div>
      {top}
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
            className={`lane-body ml-body ${edge ? "is-edge" : ""}`}
            onPointerDown={down}
            onPointerMove={move}
            onPointerLeave={() => {
              if (!drag.current) setEdge(false);
              dropPop();
            }}
            onPointerUp={up}
            onPointerCancel={up}
            onContextMenu={context}
            role="presentation"
            data-testid={`lane-${tr.name}`}
            data-track={tr.name}
          >
            {!tiles.size &&
              tr.clips
                .filter(([a, b]) => b >= t0 && a <= t1)
                .map(([a, b]) => <div key={a} className={`clip clip-${i} ml-clip`} style={{ left: x(Math.max(a, t0)), width: w(a, b) }} />)}
            <Wave index={i} name={tr.name} tiles={tiles} t0={t0} span={span} />
            {visible.map((e) => {
              if (e.tracks && !e.tracks.includes(tr.name)) return null;
              if (e.status === "restored" || (e.tracks && e.status === "applied"))
                return <div key={e.id} className={`mark-span ${e.status}`} style={{ left: x(Math.max(e.t, t0)), width: w(e.t, e.t + e.len) }} title={popover ? undefined : e.title} data-title={e.title} />;
              return <div key={e.id} className={`mark-cut ${pop?.id === e.id ? "is-hot" : ""}`} style={{ left: x(e.t) }} title={popover ? undefined : e.title} data-title={e.title} />;
            })}
            {highlight && highlight.t + highlight.len >= t0 && highlight.t <= t1 && (
              <div
                className="mark-pending"
                style={{ left: x(Math.max(highlight.t, t0)), width: w(highlight.t, highlight.t + Math.max(highlight.len, 0.3)) }}
                title={highlight.title}
              />
            )}
            {showSel && (
              <div
                className="ml-sel"
                style={{ left: x(Math.max(sel.a, t0)), width: w(sel.a, sel.b) }}
                data-testid="ml-sel"
                data-a={sel.a.toFixed(2)}
                data-b={sel.b.toFixed(2)}
              />
            )}
            {time >= t0 && time <= t1 && <div className="ml-head-line" style={{ left: x(time) }} />}
          </div>
        </div>
      ))}
      {menuOpen && lanesSel && <LaneMenu ref={menu} ep={ep} m={m} left={menuAt?.left ?? 0} top={menuAt?.top ?? 0} hidden={!menuAt} />}
      {bottom}
      {pop && popover && (() => {
        const ed = ep.edits.find((x) => x.id === pop.id);
        return ed ? (
          <div className="ml-pop" style={{ left: pop.left, top: pop.top }} onPointerEnter={keepPop} onPointerLeave={() => dropPop()} data-testid="ml-pop">
            {popover(ed)}
          </div>
        ) : null;
      })()}
    </section>
  );
}
