import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { EditInfo, Episode } from "../../api";
import { fmt } from "../../api";
import type { Player } from "../../usePlayer";
import { t } from "../../i18n";
import { manualApi, TILE_S } from "./api";
import type { WaveTile } from "./api";
import { range, useChunks } from "./chunks";
import { SelBar } from "./SelBar";
import { MIN_SEL } from "./useManual";
import type { Manual } from "./useManual";
import "./manual.css";

const ZOOMS = [10, 30, 60] as const;
const ZOOM_KEY = "lacuna.manual.zoom";
const WHEEL_GAP_MS = 150;
const EDGE_PX = 7; // grab a selection edge within this many pixels

const readZoom = (): number => {
  try {
    const z = Number(localStorage.getItem(ZOOM_KEY));
    return (ZOOMS as readonly number[]).includes(z) ? z : 30;
  } catch {
    return 30;
  }
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

/**
 * The timeline of 整集试听 with manual editing: each host's real waveform, zoom, and drag to select a stretch
 * (decision manual-editing). The selection is shared with the transcript card (TranscriptEdit).
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
  const [zoom, setZoom] = useState(readZoom);
  const [frozen, setFrozen] = useState<number | null>(null); // window start held still while dragging
  const drag = useRef<{ x0: number; anchor: number; moved: boolean; r: DOMRect; win: number } | null>(null);
  const { sel, setSel } = m;
  const d = ep.duration;
  const span = zoom;
  const t0 = frozen ?? Math.max(0, Math.min(time - span / 2, d - span));
  const t1 = t0 + span;

  // Ctrl + wheel over this card zooms the timeline, not the page (Leon 2026-10-20). React's onWheel is
  // passive, so the page zoom can only be stopped from a listener added by hand. One step per notch;
  // a trackpad pinch sends a burst of small events, so steps are at least WHEEL_GAP_MS apart.
  const card = useRef<HTMLElement | null>(null);
  useEffect(() => {
    const el = card.current;
    if (!el) return;
    let last = 0;
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey || e.deltaY === 0) return;
      e.preventDefault();
      if (e.timeStamp - last < WHEEL_GAP_MS) return;
      last = e.timeStamp;
      setZoom((z) => {
        const i = ZOOMS.indexOf(z as (typeof ZOOMS)[number]) + (e.deltaY < 0 ? -1 : 1);
        return ZOOMS[Math.max(0, Math.min(ZOOMS.length - 1, i))];
      });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(ZOOM_KEY, String(zoom));
    } catch {
      /* storage unavailable */
    }
  }, [zoom]);

  const tiles = useChunks<WaveTile>(ep.version, range(Math.floor(t0 / TILE_S), Math.floor(Math.min(t1, d) / TILE_S)), (k) =>
    manualApi.wave(ep.id, ep.version, k),
  );

  const x = (s: number) => `${(100 * (s - t0)) / span}%`;
  const w = (a: number, b: number) => `${(100 * Math.max(0, Math.min(b, t1) - Math.max(a, t0))) / span}%`;
  const at = (clientX: number, r: DOMRect, win: number) => Math.max(0, Math.min(d, win + ((clientX - r.left) / r.width) * span));

  const down = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    const r = e.currentTarget.getBoundingClientRect();
    let anchor = at(e.clientX, r, t0);
    let moved = false;
    if (sel) {
      const px = (s: number) => r.left + ((s - t0) / span) * r.width;
      if (Math.abs(e.clientX - px(sel.a)) <= EDGE_PX) [anchor, moved] = [sel.b, true];
      else if (Math.abs(e.clientX - px(sel.b)) <= EDGE_PX) [anchor, moved] = [sel.a, true];
    }
    drag.current = { x0: e.clientX, anchor, moved, r, win: t0 };
    setFrozen(t0);
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const move = (e: React.PointerEvent<HTMLDivElement>) => {
    const g = drag.current;
    if (!g) return;
    if (!g.moved && Math.abs(e.clientX - g.x0) < 4) return;
    g.moved = true;
    const s = at(e.clientX, g.r, g.win);
    setSel({ a: Math.min(g.anchor, s), b: Math.max(g.anchor, s), from: "lanes" });
  };
  const up = (e: React.PointerEvent<HTMLDivElement>) => {
    const g = drag.current;
    drag.current = null;
    setFrozen(null);
    if (!g) return;
    if (!g.moved) {
      setSel(null);
      player.seek(at(e.clientX, g.r, g.win));
    } else setSel((s) => (s && s.b - s.a >= MIN_SEL ? s : null));
  };

  const visible = ep.edits.filter((e) => e.category !== "loudness" && e.t + e.len >= t0 && e.t <= t1);
  const ticks = [0, 1, 2, 3].map((i) => t0 + (i * span) / 3);
  const showSel = sel && sel.b > t0 && sel.a < t1;
  return (
    <section ref={card} className="card lanes ml" aria-label={t("剪辑时间线")} data-testid="edit-lanes">
      <div className="ml-head">
        <h2>{t("剪辑时间线")}</h2>
        <span className="grow" />
        <span className="muted small">{t("拖动选一段来剪 · 点一下跳到那里")}</span>
        <span className="ml-zoom" role="group" aria-label={t("缩放")}>
          {ZOOMS.map((z) => (
            <button key={z} type="button" aria-pressed={zoom === z} onClick={() => setZoom(z)}>
              {t("{n} 秒", { n: z })}
            </button>
          ))}
        </span>
      </div>
      <div className="lane-ticks mono small muted" aria-hidden>
        {ticks.map((s) => (
          <span key={s}>{fmt(s)}</span>
        ))}
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
