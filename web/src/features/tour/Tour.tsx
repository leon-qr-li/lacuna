// The bubble tour engine (new-user batch, tour v3): a mask with one lit hole, a ring and a bubble. Only the hole
// can be clicked on a do step; a 知道了 step blocks it too (unless `free`). The place reached is kept on the
// server (onboarding `tour`), so leaving and coming back resumes it. Only in LACUNA 示例节目.
import { Fragment, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { AB, Episode } from "../../api";
import { fmt, req } from "../../api";
import type { Player } from "../../usePlayer";
import { t } from "../../i18n";
import { confirmDialog } from "../dialog/Dialog";
import { libraryApi } from "../library/api";
import { onboardingApi, setOnboarding, useOnboarding } from "../onboarding/api";
import { openProject, useProjects } from "../projects/api";
import { CHAPTERS, chapterName, DONE, STEPS, type Ctx, type Hosts, type Marks, type Step } from "./steps";
import "./tour.css";

type Rect = { x: number; y: number; w: number; h: number };
const PAD = 8;
const GAP = 16;

const visible = (el: Element) => {
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0 ? r : null;
};
function union(rs: DOMRect[]): Rect | null {
  if (!rs.length) return null;
  const x0 = Math.min(...rs.map((r) => r.left));
  const y0 = Math.min(...rs.map((r) => r.top));
  const x1 = Math.max(...rs.map((r) => r.right));
  const y1 = Math.max(...rs.map((r) => r.bottom));
  // clipped to the window, padded
  const x = Math.max(4, x0 - PAD);
  const y = Math.max(4, y0 - PAD);
  const w = Math.min(window.innerWidth - 4, x1 + PAD) - x;
  const h = Math.min(window.innerHeight - 4, y1 + PAD) - y;
  return w > 0 && h > 0 ? { x, y, w, h } : null;
}
const same = (a: Rect | null, b: Rect | null) =>
  a === b || (!!a && !!b && Math.abs(a.x - b.x) < 0.5 && Math.abs(a.y - b.y) < 0.5 && Math.abs(a.w - b.w) < 0.5 && Math.abs(a.h - b.h) < 0.5);

/** **bold** in a bubble's text */
function rich(s: string): ReactNode {
  return s.split(/\*\*(.+?)\*\*/g).map((part, i) => (i % 2 ? <b key={i}>{part}</b> : <Fragment key={i}>{part}</Fragment>));
}

function elements(s: Step, c: Ctx): Element[] {
  return (s.target ?? []).flatMap((x) => (typeof x === "string" ? [...document.querySelectorAll(x)] : x(c)));
}

/** Where the bubble goes: the preferred side when it fits, else the first side that fits, else a corner. */
function place(hole: Rect | null, size: { w: number; h: number }, side: Step["side"]): { left: number; top: number } {
  const W = window.innerWidth;
  const H = window.innerHeight;
  const clampX = (x: number) => Math.max(12, Math.min(W - size.w - 12, x));
  const clampY = (y: number) => Math.max(12, Math.min(H - size.h - 12, y));
  if (!hole) return { left: (W - size.w) / 2, top: (H - size.h) / 2 };
  const opts = {
    bottom: { left: clampX(hole.x), top: hole.y + hole.h + GAP, ok: hole.y + hole.h + GAP + size.h <= H - 8 },
    top: { left: clampX(hole.x), top: hole.y - GAP - size.h, ok: hole.y - GAP - size.h >= 8 },
    right: { left: hole.x + hole.w + GAP, top: clampY(hole.y), ok: hole.x + hole.w + GAP + size.w <= W - 8 },
    left: { left: hole.x - GAP - size.w, top: clampY(hole.y), ok: hole.x - GAP - size.w >= 8 },
  };
  const order = [side ?? "bottom", "bottom", "right", "top", "left"] as const;
  const pick = order.map((k) => opts[k]).find((o) => o.ok);
  if (pick) return { left: pick.left, top: pick.top };
  return { left: W - size.w - 16, top: H - size.h - 16 };
}

export function Tour({ ep, mode, id, player }: { ep: Episode; mode: string; id: string; player: Player }) {
  const ob = useOnboarding();
  const sp = useProjects();
  const on = !!ob?.sample && !!sp?.current?.sample && ob.sample.episode === id;
  const at = ob?.tour;
  if (!on || !ob) return null;
  if (at === "") return <Restart />;
  if (at?.startsWith("~")) return <Resume at={at.slice(1)} />;
  return <Run ep={ep} mode={mode} id={id} player={player} at={at ?? STEPS[0].id} />;
}

/** After the tour: start it again (the sample goes back to the first cut). */
function Restart() {
  const again = async () => {
    if (!(await confirmDialog({ message: t("示例集会回到 LACUNA 第一刀刚做完的样子，你在里面做的改动都会清掉，然后从头开始教程。"), confirmLabel: t("重新开始") })))
      return;
    const o = await onboardingApi.resetSample();
    window.location.hash = `#/ep/${encodeURIComponent(o.sample?.episode ?? "SAMPLE_01")}/review`;
    window.location.reload();
  };
  return (
    <button type="button" className="tour-again" onClick={() => void again()} data-testid="tour-again">
      {t("重新开始示例教程")}
    </button>
  );
}

/** Left halfway with ×: one click goes on from the same step. */
function Resume({ at }: { at: string }) {
  return (
    <button type="button" className="tour-again" onClick={() => save(at)} data-testid="tour-resume">
      {t("继续示例教程")}
    </button>
  );
}

function save(step: string) {
  onboardingApi.flags({ tour: step }).then(setOnboarding, () => undefined);
}

function Run({ ep, mode, id, player, at }: { ep: Episode; mode: string; id: string; player: Player; at: string }) {
  const [cur, setCur] = useState(() => Math.max(0, STEPS.findIndex((s) => s.id === at)));
  const [finished, setFinished] = useState(at === DONE);
  const [marks, setMarks] = useState<Marks | null>(null);
  const step = finished ? null : STEPS[cur];
  const memo = useRef<Record<string, unknown>>({});
  const clicked = useRef(new Set<string>());
  const [, setTick] = useState(0);

  useEffect(() => {
    req<Marks>("GET", `/api/episodes/${encodeURIComponent(id)}/tour/marks`).then(setMarks, () => setMarks(null));
  }, [id, ep.version]);

  const ctx = useRef<Ctx>(null as unknown as Ctx);
  ctx.current = { ep, id, mode, marks, player, memo: memo.current, clicked: clicked.current };
  const h: Hosts = { a: marks?.hosts[0] ?? ep.tracks[0]?.name ?? "", b: marks?.hosts[1] ?? ep.tracks[1]?.name ?? "" };

  const go = useCallback((i: number) => {
    stopAudio(); // every new step starts quiet: the page is masked, so nothing else could stop it
    memo.current = {};
    clicked.current = new Set();
    if (i >= STEPS.length) {
      setFinished(true);
      save(DONE);
      return;
    }
    STEPS[i].init?.({ ...ctx.current, memo: memo.current, clicked: clicked.current });
    setCur(i);
    save(STEPS[i].id);
  }, []);
  const next = useCallback(() => go(cur + 1), [go, cur]);

  // on the step's page; its enter once the page is there
  const entered = useRef<string | null>(null); // the step whose enter has run: only then is it checked
  useEffect(() => {
    if (!step) return;
    // a "下一步" step is done on the next page; any other step is shown on its own page
    const moved = !step.clicks && !!step.done?.(ctx.current);
    if (mode !== step.mode && !moved) {
      window.location.hash = `#/ep/${encodeURIComponent(id)}/${step.mode}`;
      return;
    }
    if (entered.current === step.id) return;
    const s = step;
    // resumed here (not reached by go): note the baseline now
    if (s.init && !Object.keys(memo.current).length) s.init(ctx.current);
    const k = window.setTimeout(() => {
      s.enter?.(ctx.current);
      entered.current = s.id;
    }, 150);
    return () => window.clearTimeout(k);
  }, [step, mode, id]);

  // clicks the step waits for
  useEffect(() => {
    if (!step?.clicks) return;
    const sels = step.clicks;
    const on = (e: MouseEvent) => {
      const el = e.target as Element | null;
      for (const s of sels) if (el?.closest?.(s)) clicked.current.add(s);
    };
    document.addEventListener("click", on, true);
    return () => document.removeEventListener("click", on, true);
  }, [step]);

  // a do step: check it a few times a second
  useEffect(() => {
    if (!step || (!step.done && !step.clicks)) return;
    const s = step;
    const k = window.setInterval(() => {
      if (entered.current !== s.id) return;
      const c = ctx.current;
      const all = (s.clicks ?? []).every((x) => c.clicked.has(x));
      if (all && (s.done ? s.done(c) : true)) next();
      else setTick((n) => n + 1);
    }, 250);
    return () => window.clearInterval(k);
  }, [step, next]);

  const exit = async () => {
    const left = STEPS.length - cur;
    const stay = await confirmDialog({
      title: t("还剩 {n} 步，大约 {m} 分钟", { n: CHAPTERS - (step?.ch ?? 1) + 1, m: Math.max(1, Math.round((left * 8) / 60)) }),
      message: t("走完你就亲手剪好了一集，最后会放剪前剪后的对比给你听。现在离开也没关系，我们记得你走到哪儿，下次打开示例节目接着走。"),
      confirmLabel: t("继续教程"),
      cancelLabel: t("先离开，下次接着走"),
    });
    if (stay || !step) return;
    stopAudio();
    setOnboarding({ ...(await onboardingApi.flags({ tour: `~${step.id}` })) });
  };

  if (finished) return <Done ep={ep} id={id} onExit={() => onboardingApi.flags({ tour: "" }).then(setOnboarding)} />;
  if (!step) return null;
  if (step.id === "raw") return <Raw step={step} id={id} h={h} onNext={next} onExit={() => void exit()} />;
  return <Mask key={step.id} step={step} ctx={ctx} h={h} onNext={next} onExit={() => void exit()} />;
}

/** Pause every player on the page (main, A/B, music clips, the raw recording). */
function stopAudio() {
  document.querySelectorAll("audio").forEach((a) => a.pause());
}

/** Something is playing somewhere on the page (polled: the players live in many components). */
function usePlaying() {
  const [on, setOn] = useState(false);
  useEffect(() => {
    const k = window.setInterval(() => setOn([...document.querySelectorAll("audio")].some((a) => !a.paused)), 300);
    return () => window.clearInterval(k);
  }, []);
  return on;
}

function Pill({ ch, onExit }: { ch: number; onExit: () => void }) {
  const playing = usePlaying();
  return (
    <div className="tour-pill" data-testid="tour-pill">
      <span>{t("示例教程 · 第 {n} 步，共 {total} 步", { n: ch, total: CHAPTERS })}</span>
      <span className="tour-dots" aria-hidden="true">
        {Array.from({ length: CHAPTERS }, (_, i) => (
          <i key={i} className={i + 1 < ch ? "is-done" : i + 1 === ch ? "is-now" : ""} />
        ))}
      </span>
      {playing && (
        <button type="button" className="tour-pill-btn" onClick={stopAudio} data-testid="tour-pause">
          {t("⏸ 暂停播放")}
        </button>
      )}
      <button type="button" className="tour-pill-x" onClick={onExit} aria-label={t("暂停教程")} title={t("暂停教程")} data-testid="tour-exit">
        ×
      </button>
    </div>
  );
}

function Mask({ step, ctx, h, onNext, onExit }: { step: Step; ctx: React.MutableRefObject<Ctx>; h: Hosts; onNext: () => void; onExit: () => void }) {
  const [hole, setHole] = useState<Rect | null>(null);
  const [box, setBox] = useState<Rect | null>(null);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  const bubble = useRef<HTMLDivElement>(null);
  const scrolled = useRef(false);

  // follow the lit part every frame (the page scrolls, popups open, the timeline moves)
  useLayoutEffect(() => {
    let raf = 0;
    const loop = () => {
      const c = ctx.current;
      const els = elements(step, c);
      const rs = els.map(visible).filter((r): r is DOMRect => !!r);
      if (!scrolled.current && els.length && rs.length) {
        scrolled.current = true;
        const r = rs[0];
        if (r.top < 70 || r.bottom > window.innerHeight - 10) els[0].scrollIntoView({ block: "center" });
      }
      const nh = union(rs);
      setHole((o) => (same(o, nh) ? o : nh));
      // the dashed box on the timeline
      const bx = step.box?.(c) ?? null;
      let nb: Rect | null = null;
      const lanes = document.querySelector<HTMLElement>('[data-testid="edit-lanes"]');
      if (bx && lanes) {
        const t0 = Number(lanes.dataset.start);
        const span = Number(lanes.dataset.span);
        const bodies = [...lanes.querySelectorAll<HTMLElement>(".ml-body")].filter((b) => !bx.track || b.dataset.track === bx.track);
        const r = union(bodies.map((b) => b.getBoundingClientRect()));
        if (r && span > 0 && bodies.length) {
          const br = bodies[0].getBoundingClientRect();
          const x0 = br.left + ((bx.a - t0) / span) * br.width;
          const x1 = br.left + ((bx.b - t0) / span) * br.width;
          const top = Math.min(...bodies.map((b) => b.getBoundingClientRect().top));
          const bottom = Math.max(...bodies.map((b) => b.getBoundingClientRect().bottom));
          if (x1 > br.left && x0 < br.right) nb = { x: Math.max(br.left, x0), y: top + 2, w: Math.min(br.right, x1) - Math.max(br.left, x0), h: bottom - top - 4 };
        }
      }
      setBox((o) => (same(o, nb) ? o : nb));
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [step, ctx]);

  useLayoutEffect(() => {
    const b = bubble.current;
    if (!b) return;
    const p = place(hole, { w: b.offsetWidth, h: b.offsetHeight }, step.side);
    setPos((o) => (o && Math.abs(o.left - p.left) < 0.5 && Math.abs(o.top - p.top) < 0.5 ? o : p));
  });

  const all = STEPS.filter((s) => s.ch === step.ch);
  const k = all.indexOf(step) + 1;
  const isDo = !!(step.done || step.clicks);
  const W = typeof window === "undefined" ? 0 : window.innerWidth;
  const H = typeof window === "undefined" ? 0 : window.innerHeight;
  // the four shades around the hole catch every click outside it; React's handler stops the page's own
  // "click outside closes it" listeners (the timeline menu) from seeing clicks on the tour
  const stop = (e: React.PointerEvent | React.MouseEvent) => e.stopPropagation();
  const shades: Rect[] = hole
    ? [
        { x: 0, y: 0, w: W, h: hole.y },
        { x: 0, y: hole.y + hole.h, w: W, h: H - hole.y - hole.h },
        { x: 0, y: hole.y, w: hole.x, h: hole.h },
        { x: hole.x + hole.w, y: hole.y, w: W - hole.x - hole.w, h: hole.h },
      ]
    : [{ x: 0, y: 0, w: W, h: H }];
  return (
    <div className="tour" data-testid="tour" data-step={step.id} onPointerDown={stop} onMouseDown={stop}>
      {shades.map((r, i) => (
        <div key={i} className="tour-shade" style={{ left: r.x, top: r.y, width: r.w, height: r.h }} />
      ))}
      {hole && <div className="tour-ring" style={{ left: hole.x, top: hole.y, width: hole.w, height: hole.h }} />}
      {hole && !isDo && !step.free && <div className="tour-block" style={{ left: hole.x, top: hole.y, width: hole.w, height: hole.h }} />}
      {box && <div className="tour-box" style={{ left: box.x, top: box.y, width: box.w, height: box.h }} data-testid="tour-box" />}
      <Pill ch={step.ch} onExit={onExit} />
      <div
        ref={bubble}
        className="tour-bubble"
        role="dialog"
        aria-label={step.title(h)}
        style={pos ? { left: pos.left, top: pos.top } : { visibility: "hidden" }}
        data-testid="tour-bubble"
      >
        <span className="tour-meta">
          {t("第 {n} 步，共 {total} 步", { n: step.ch, total: CHAPTERS })} · {chapterName(step.ch)} · {k}/{all.length}
        </span>
        <h3>{step.title(h)}</h3>
        <p>{rich(step.body(h))}</p>
        <div className="tour-foot">
          {isDo && <span className="tour-hint">{step.hint?.(h)}</span>}
          {(!isDo || step.alsoOk) && (
            <button type="button" className="btn btn-primary btn-small" onClick={onNext} data-testid="tour-ok" autoFocus>
              {t("知道了")}
            </button>
          )}
          <span className="grow" />
          {isDo && !step.alsoOk && (
            <button type="button" className="linkbtn small" onClick={onNext} data-testid="tour-skip-step">
              {t("跳过这一步")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/** 1: the first 30 seconds as recorded, before anything else */
function Raw({ step, id, h, onNext, onExit }: { step: Step; id: string; h: Hosts; onNext: () => void; onExit: () => void }) {
  const [ab, setAb] = useState<AB | null>(null);
  const [playing, setPlaying] = useState(false);
  const [now, setNow] = useState(0);
  const audio = useRef<HTMLAudioElement>(null);
  useEffect(() => {
    req<AB>("GET", `/api/episodes/${encodeURIComponent(id)}/tour/raw`).then(setAb, () => undefined);
  }, [id]);
  const toggle = () => {
    const a = audio.current;
    if (!a) return;
    if (a.paused) void a.play().catch(() => undefined);
    else a.pause();
  };
  return (
    <div className="tour" data-testid="tour" data-step={step.id}>
      <div className="tour-shade" style={{ inset: 0 }} />
      <Pill ch={1} onExit={onExit} />
      <div className="tour-modal card" role="dialog" aria-label={step.title(h)} data-testid="tour-raw">
        <span className="tour-meta">{t("第 {n} 步，共 {total} 步", { n: 1, total: CHAPTERS })} · {chapterName(1)}</span>
        <h2>{step.title(h)}</h2>
        <p>{rich(step.body(h))}</p>
        <div className="tour-play">
          <button type="button" className="btn btn-primary" onClick={toggle} disabled={!ab} data-testid="tour-raw-play">
            {playing ? t("❚❚ 暂停") : t("▶ 播放原始录音")}
          </button>
          <span className="mono small">
            {fmt(now)} / {fmt(ab?.before.duration ?? 30)}
          </span>
        </div>
        <audio
          ref={audio}
          src={ab?.before.url}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onTimeUpdate={(e) => setNow(e.currentTarget.currentTime)}
          onEnded={onNext}
          data-testid="tour-raw-audio"
        />
        <div className="tour-foot">
          <span className="tour-hint">{t("听完自动进入下一步。")}</span>
          <span className="grow" />
          <button type="button" className="btn btn-outline btn-small" onClick={onNext} data-testid="tour-ok">
            {t("下一步")}
          </button>
        </div>
        <p className="tour-note small muted">{t("示例节目不占用你的额度。两位主持人的声音是合成的。")}</p>
      </div>
    </div>
  );
}

/** 10: the same 30 seconds before and after, what was done, and where to go now */
function Done({ ep, id, onExit }: { ep: Episode; id: string; onExit: () => Promise<unknown> }) {
  const sp = useProjects();
  const [raw, setRaw] = useState<string | null>(null);
  const [mix, setMix] = useState<{ url: string; duration: number; n: number } | null>(null);
  const [playing, setPlaying] = useState<"before" | "after" | null>(null);
  const before = useRef<HTMLAudioElement>(null);
  const after = useRef<HTMLAudioElement>(null);
  useEffect(() => {
    req<AB>("GET", `/api/episodes/${encodeURIComponent(id)}/tour/raw`).then((ab) => setRaw(ab.before.url), () => undefined);
    libraryApi.music(id).then((m) => setMix({ url: m.mix_url, duration: m.duration ?? ep.duration, n: m.placements.length }), () => undefined);
  }, [id, ep.duration]);
  const play = (side: "before" | "after") => {
    const [a, b] = side === "before" ? [before.current, after.current] : [after.current, before.current];
    b?.pause();
    if (!a) return;
    if (playing === side) return a.pause();
    a.currentTime = 0;
    void a.play().catch(() => undefined);
  };
  const stopAt30 = (e: React.SyntheticEvent<HTMLAudioElement>) => e.currentTarget.currentTime >= 30 && e.currentTarget.pause();
  const reviewed = ep.edits.filter((e) => e.consequential).length;
  const manual = ep.edits.filter((e) => e.source === "manual" || e.source === "chat").length;
  const own = sp?.mine.find((m) => !m.sample && !m.archived && !m.support);
  const leave = async (to: () => void) => {
    await onExit();
    to();
  };
  const again = async () => {
    const o = await onboardingApi.resetSample();
    window.location.hash = `#/ep/${encodeURIComponent(o.sample?.episode ?? id)}/review`;
    window.location.reload();
  };
  const stats = useMemo(
    () => [
      t("剪辑 {a} → {b}", { a: fmt(ep.raw_duration ?? ep.duration), b: fmt(ep.duration) }),
      t("成品含配乐 {c}", { c: fmt(mix?.duration ?? ep.duration) }),
      t("你审阅了 {n} 处", { n: reviewed }),
      t("你动手剪了 {n} 处", { n: manual }),
      t("配乐 {n} 段", { n: mix?.n ?? 0 }),
    ],
    [ep, mix, reviewed, manual],
  );
  return (
    <div className="tour" data-testid="tour" data-step="done">
      <div className="tour-shade" style={{ inset: 0 }} />
      <div className="tour-modal tour-done card" role="dialog" aria-label={t("示例完成")} data-testid="tour-done">
        <span className="tour-meta tour-ok-meta">{t("示例完成")}</span>
        <h2>{t("同一段 30 秒，剪之前和剪之后")}</h2>
        <div className="tour-ab">
          <button type="button" className={`tour-side ${playing === "before" ? "is-on" : ""}`} onClick={() => play("before")} disabled={!raw} data-testid="tour-before">
            <span className="tour-side-play">{playing === "before" ? "❚❚" : "▶"}</span>
            <span>
              <strong>{t("剪之前")}</strong>
              <span className="small muted">{t("原始录音 · 0:30")}</span>
              <span className="small muted">{t("重说 · 口头禅 · 冷场 · 跑题 · 音量一大一小")}</span>
            </span>
          </button>
          <button type="button" className={`tour-side is-after ${playing === "after" ? "is-on" : ""}`} onClick={() => play("after")} disabled={!mix} data-testid="tour-after">
            <span className="tour-side-play">{playing === "after" ? "❚❚" : "▶"}</span>
            <span>
              <strong>{t("剪之后")}</strong>
              <span className="small muted">{t("成品前 30 秒 · 带配乐")}</span>
              <span className="small muted">{t("紧凑、两人一样大声、对话的节奏和笑声都还在")}</span>
            </span>
          </button>
        </div>
        <audio ref={before} src={raw ?? undefined} onPlay={() => setPlaying("before")} onPause={() => setPlaying((p) => (p === "before" ? null : p))} onTimeUpdate={stopAt30} />
        <audio ref={after} src={mix?.url} onPlay={() => setPlaying("after")} onPause={() => setPlaying((p) => (p === "after" ? null : p))} onTimeUpdate={stopAt30} />
        <div className="tour-stats">
          {stats.map((x) => (
            <b key={x}>{x}</b>
          ))}
        </div>
        <div className="tour-done-acts">
          <button type="button" className="btn btn-primary" onClick={() => void leave(() => (own ? void openProject(own.id) : (window.location.hash = "#/projects")))} data-testid="tour-own">
            {t("导入我自己的第一集")}
          </button>
          <button type="button" className="btn btn-outline" onClick={() => void again()} data-testid="tour-again-run">
            {t("再走一遍示例")}
          </button>
          <button type="button" className="btn btn-outline" onClick={() => void leave(() => (window.location.hash = `#/ep/${encodeURIComponent(id)}/publish`))} data-testid="tour-publish">
            {t("去看看「发布」")}
          </button>
        </div>
        <p className="small muted">{t("示例节目会留在你的节目列表里，可以随便点；不想要了在 设置 → 通用 里删除。")}</p>
      </div>
    </div>
  );
}
