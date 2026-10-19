import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { EditInfo, Episode } from "../../api";
import { fmt } from "../../api";
import type { Player } from "../../usePlayer";
import { t } from "../../i18n";
import { manualApi, TILE_S, WORDS_S } from "./api";
import "./manual.css";
import type { Utterance, WaveTile } from "./api";

const ZOOMS = [10, 30, 60] as const;
const ZOOM_KEY = "lacuna.manual.zoom";
const MIN_SEL = 0.05; // seconds; a shorter drag is a click
const EDGE_PX = 7; // grab a selection edge within this many pixels

type Sel = { a: number; b: number };

const readZoom = (): number => {
  try {
    const z = Number(localStorage.getItem(ZOOM_KEY));
    return (ZOOMS as readonly number[]).includes(z) ? z : 30;
  } catch {
    return 30;
  }
};

/** Fetch-once cache of per-version chunks (waveform tiles, transcript stretches); re-renders on arrival. */
function useChunks<T>(version: string, keys: number[], load: (k: number) => Promise<T>): Map<number, T> {
  const cache = useRef(new Map<string, T | null>());
  const [, bump] = useState(0);
  const sig = keys.join(",");
  useEffect(() => {
    let live = true;
    for (const k of keys) {
      const key = `${version}:${k}`;
      if (cache.current.has(key)) continue;
      cache.current.set(key, null);
      load(k).then(
        (v) => {
          cache.current.set(key, v);
          if (live) bump((n) => n + 1);
        },
        () => cache.current.delete(key),
      );
    }
    if (cache.current.size > 400) {
      for (const key of [...cache.current.keys()]) if (!key.startsWith(`${version}:`)) cache.current.delete(key);
    }
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version, sig]);
  const out = new Map<number, T>();
  for (const k of keys) {
    const v = cache.current.get(`${version}:${k}`);
    if (v) out.set(k, v);
  }
  return out;
}

/** m:ss.s - a selection needs tenths */
const fmtTenths = (s: number) => {
  const m = Math.floor(s / 60);
  const r = s - m * 60;
  return `${m}:${r.toFixed(1).padStart(4, "0")}`;
};

const range = (a: number, b: number) => Array.from({ length: Math.max(0, b - a + 1) }, (_, i) => a + i);

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
 * The two-track (or more) timeline of 整集试听 with manual editing: real waveforms, zoom, drag to select a
 * stretch (on the waveform or on the transcript below), then cut it from every track or silence one host.
 * Edits made here are ordinary edits: undo, 恢复 in the lists, and the AI producer all see them.
 */
export function EditLanes({
  ep,
  time,
  player,
  highlight,
  run,
}: {
  ep: Episode;
  time: number;
  player: Player;
  highlight?: EditInfo | null;
  run: (p: Promise<Episode>, msg?: string) => Promise<boolean>;
}) {
  const [zoom, setZoom] = useState(readZoom);
  const [sel, setSel] = useState<Sel | null>(null);
  const [frozen, setFrozen] = useState<number | null>(null); // window start held still while dragging
  const [busy, setBusy] = useState(false);
  // a drag on the waveform (r = the lane's box) or across transcript words (word: anchor..end = first word)
  const drag = useRef<{ x0: number; anchor: number; end?: number; moved: boolean; r: DOMRect; win: number; word?: boolean } | null>(null);
  const stopAt = useRef<number | null>(null);
  const d = ep.duration;
  const span = zoom;
  const live = Math.max(0, Math.min(time - span / 2, d - span));
  const t0 = frozen ?? live;
  const t1 = t0 + span;

  useEffect(() => {
    try {
      localStorage.setItem(ZOOM_KEY, String(zoom));
    } catch {
      /* storage unavailable */
    }
  }, [zoom]);
  useEffect(() => setSel(null), [ep.version]); // a new cut moves everything after it

  const tiles = useChunks<WaveTile>(ep.version, range(Math.floor(t0 / TILE_S), Math.floor(Math.min(t1, d) / TILE_S)), (k) =>
    manualApi.wave(ep.id, ep.version, k),
  );
  const chunks = useChunks<Utterance[]>(
    ep.version,
    ep.has_transcript ? range(Math.floor(t0 / WORDS_S), Math.floor(Math.min(t1, d) / WORDS_S)) : [],
    (k) => manualApi.words(ep.id, ep.version, k * WORDS_S, (k + 1) * WORDS_S).then((r) => r.utterances),
  );
  const words = useMemo(() => {
    const seen = new Set<string>();
    const out: { text: string; a: number; b: number; speaker: string }[] = [];
    for (const us of chunks.values())
      for (const u of us)
        for (const [text, a, b] of u.words) {
          const k = `${u.speaker}:${a}`;
          if (seen.has(k) || b < t0 || a > t1) continue;
          seen.add(k);
          out.push({ text, a, b, speaker: u.speaker });
        }
    return out.sort((x, y) => x.a - y.a);
  }, [chunks, t0, t1]);

  // ▶ 听选中: stop at the end of the selection (without the rewind-on-pause)
  useEffect(() => {
    if (stopAt.current !== null && time >= stopAt.current) {
      stopAt.current = null;
      player.ref.current?.pause();
    }
  }, [time, player]);

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
    if (!g || g.word) return;
    if (!g.moved && Math.abs(e.clientX - g.x0) < 4) return;
    g.moved = true;
    const s = at(e.clientX, g.r, g.win);
    setSel({ a: Math.min(g.anchor, s), b: Math.max(g.anchor, s) });
  };
  const up = (e: React.PointerEvent<HTMLDivElement>) => {
    const g = drag.current;
    drag.current = null;
    setFrozen(null);
    if (!g || g.word) return;
    if (!g.moved) {
      setSel(null);
      player.seek(at(e.clientX, g.r, g.win));
    } else setSel((s) => (s && s.b - s.a >= MIN_SEL ? s : null));
  };

  // transcript: press on a word and drag across others; a plain click jumps there
  const wordDown = (wd: { a: number; b: number }) => (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    e.preventDefault();
    drag.current = { x0: e.clientX, anchor: wd.a, end: wd.b, moved: false, r: new DOMRect(), win: t0, word: true };
    setFrozen(t0);
    setSel({ a: wd.a, b: wd.b });
  };
  const wordEnter = (wd: { a: number; b: number }) => () => {
    const g = drag.current;
    if (!g?.word) return;
    g.moved = true;
    setSel({ a: Math.min(g.anchor, wd.a), b: Math.max(g.end ?? g.anchor, wd.b) });
  };
  useEffect(() => {
    const end = () => {
      const g = drag.current;
      if (!g?.word) return;
      drag.current = null;
      setFrozen(null);
      if (!g.moved) {
        setSel(null);
        player.seek(g.anchor);
      }
    };
    window.addEventListener("pointerup", end);
    return () => window.removeEventListener("pointerup", end);
  }, [player]);

  const cut = useCallback(
    async (track: string | null) => {
      if (!sel || busy) return;
      setBusy(true);
      const s = (sel.b - sel.a).toFixed(1);
      const ok = await run(
        manualApi.cut(ep.id, sel.a, sel.b, track, Math.max(0, sel.a - 2)),
        track ? t("已静音 {track} {s} 秒，可撤销", { track, s }) : t("已删掉 {s} 秒，可撤销", { s }),
      );
      setBusy(false);
      if (ok) setSel(null);
    },
    [sel, busy, run, ep.id],
  );
  const listen = () => {
    if (!sel) return;
    stopAt.current = sel.b;
    player.seek(sel.a);
    player.play();
  };

  // Delete / Backspace cuts the selection from every track, Esc drops it
  useEffect(() => {
    if (!sel) return;
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key === "Delete" || e.key === "Backspace") {
        e.preventDefault();
        void cut(null);
      } else if (e.key === "Escape") setSel(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sel, cut]);

  const visible = ep.edits.filter((e) => e.category !== "loudness" && e.t + e.len >= t0 && e.t <= t1);
  const ticks = [0, 1, 2, 3].map((i) => t0 + (i * span) / 3);
  const showSel = sel && sel.b > t0 && sel.a < t1;
  const idx = (name: string) => Math.max(0, ep.tracks.findIndex((tr) => tr.name === name));
  return (
    <section className="card lanes ml" aria-label={t("剪辑时间线")} data-testid="edit-lanes">
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
      {sel && (
        <div className="ml-bar" role="toolbar" aria-label={t("选中的这一段")} data-testid="ml-bar">
          <span className="ml-what">
            {t("已选")} <b className="mono">{fmtTenths(sel.a)} – {fmtTenths(sel.b)}</b> · {t("{s} 秒", { s: (sel.b - sel.a).toFixed(1) })}
          </span>
          <span className="grow" />
          <button type="button" className="btn btn-primary btn-small" disabled={busy} onClick={() => void cut(null)} data-testid="ml-cut">
            {t("删掉这段")} <kbd className="ml-kbd">Del</kbd>
          </button>
          {ep.tracks.map((tr) => (
            <button key={tr.name} type="button" className="btn btn-outline btn-small" disabled={busy} onClick={() => void cut(tr.name)} data-testid={`ml-mute-${tr.name}`}>
              {t("只静音 {name}", { name: tr.name })}
            </button>
          ))}
          <button type="button" className="btn btn-ghost btn-small" onClick={listen} data-testid="ml-listen">
            ▶ {t("听选中")}
          </button>
          <button type="button" className="btn btn-ghost btn-small" onClick={() => setSel(null)}>
            {t("取消")} <kbd className="ml-kbd">Esc</kbd>
          </button>
        </div>
      )}
      {ep.has_transcript && (
        <div className="ml-words" data-testid="ml-words">
          {words.length === 0 ? (
            <span className="muted small">{chunks.size ? t("这一段没有人说话") : t("正在读文字稿…")}</span>
          ) : (
            words.map((wd, i) => {
              const on = sel && (wd.a + wd.b) / 2 >= sel.a && (wd.a + wd.b) / 2 < sel.b;
              const now = time >= wd.a && time < wd.b;
              return (
                <span key={`${wd.speaker}:${wd.a}`}>
                  {(i === 0 || words[i - 1].speaker !== wd.speaker) && <span className={`ml-who spk-${idx(wd.speaker) % 6}`}>{wd.speaker}</span>}
                  <span
                    className={`ml-w ${on ? "is-sel" : ""} ${now ? "is-now" : ""}`}
                    onPointerDown={wordDown(wd)}
                    onPointerEnter={wordEnter(wd)}
                    data-t={wd.a}
                  >
                    {wd.text}
                  </span>
                </span>
              );
            })
          )}
        </div>
      )}
      <p className="muted small legend">
        <span className="lg lg-cut" /> {t("剪切点")}　<span className="lg lg-lift" /> {t("单轨删减")}
        <span className="lg lg-restored" /> {t("已恢复")}　<span className="lg lg-pending" /> {t("待批准")}　<span className="lg ml-lg-sel" /> {t("你选中的")}
      </p>
    </section>
  );
}
