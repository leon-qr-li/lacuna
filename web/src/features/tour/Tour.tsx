// The bubble tour engine (new-user batch, tour v3): a mask with one lit hole, a ring and a bubble. A locked demo
// (Leon 2026-10-23, "像 PPT"): nothing on the page can be clicked and the person only presses 知道了. Reading and
// acting never overlap: a step's scene is set (`enter`) before its bubble shows; LACUNA acts (`act`) only after
// 知道了, then shows `result` or goes on, clicking 下一步 itself where the page changes. The place reached is kept on
// the server (onboarding `tour`), so leaving and coming back resumes it. Only in LACUNA 示例节目.
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
import { CHAPTERS, chapterName, DONE, STEPS, tap, until, wait, type Ctx, type Hosts, type Marks, type Step } from "./steps";
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
  // the spots on the current cut: a step only begins once they are fetched for this version
  const [got, setGot] = useState<{ v: string; m: Marks | null } | null>(null);
  const marks = got?.v === ep.version ? got.m : null;
  const fresh = got?.v === ep.version;
  const step = finished ? null : STEPS[cur];
  const memo = useRef<Record<string, unknown>>({});
  const [, setTick] = useState(0);
  const mounted = useRef(true);
  useEffect(() => () => void (mounted.current = false), []);

  useEffect(() => {
    const v = ep.version;
    req<Marks>("GET", `/api/episodes/${encodeURIComponent(id)}/tour/marks`).then((m) => setGot({ v, m }), () => setGot({ v, m: null }));
  }, [id, ep.version]);

  const ctx = useRef<Ctx>(null as unknown as Ctx);
  const m0 = memo.current;
  ctx.current = { ep, id, mode, marks, player, memo: m0, alive: () => mounted.current && memo.current === m0 };
  const h: Hosts = { a: marks?.hosts[0] ?? ep.tracks[0]?.name ?? "", b: marks?.hosts[1] ?? ep.tracks[1]?.name ?? "" };

  const [phase, setPhase] = useState<Phase>("read");
  const [ready, setReady] = useState<string | null>(null); // the step whose scene is set: its bubble may show
  const nav = useRef<HTMLElement | null>(null);
  const curRef = useRef(cur);
  curRef.current = cur;

  const go = useCallback((i: number) => {
    stopAudio(); // every new step starts quiet: the page is masked, so nothing else could stop it
    memo.current = {};
    setPhase("read");
    if (i >= STEPS.length) {
      setFinished(true);
      save(DONE);
      return;
    }
    setCur(i);
    save(STEPS[i].id);
  }, []);
  const next = useCallback(() => go(cur + 1), [go, cur]);

  // 知道了: LACUNA acts (the person has read it), maybe shows the result, then goes on, clicking the way to the
  // next page itself
  const ok = useCallback(async () => {
    const i = curRef.current;
    const s = STEPS[i];
    const live = () => mounted.current && curRef.current === i;
    if (phase === "act" || phase === "going") return;
    if (phase === "nav") {
      // read first, then LACUNA presses 下一步, slowly enough to follow
      setPhase("going");
      await wait(500);
      if (nav.current) await tap(nav.current, 1200);
      if (live()) go(i + 1);
      return;
    }
    if (phase === "read" && s.act) {
      setPhase("act");
      await s.act(ctx.current);
      if (s.done) await until(() => !live() || s.done!(ctx.current), 20_000);
      if (!live()) return;
      await wait(700); // the outcome stays on screen a moment
      if (s.result) return setPhase("result");
    }
    const nx = STEPS[i + 1];
    if (nx && nx.mode !== s.mode) {
      const link = navLink(id, nx.mode);
      if (link) {
        nav.current = link;
        return setPhase("nav");
      }
    }
    if (live()) go(i + 1);
  }, [phase, id, go]);

  // on the step's page; its enter once the page is there
  const entered = useRef<string | null>(null); // the step whose enter has run: only then is it checked
  useEffect(() => {
    if (!step) return;
    if (mode !== step.mode) {
      window.location.hash = `#/ep/${encodeURIComponent(id)}/${step.mode}`;
      return;
    }
    if (entered.current === step.id || !fresh) return;
    const s = step;
    const k = window.setTimeout(() => {
      entered.current = s.id;
      s.enter?.(ctx.current);
      // the scene settles (seek, scroll, a panel opening) before there is anything to read
      // and after a change of page, the new page shows a moment on its own first
      const moved = STEPS[STEPS.indexOf(s) - 1]?.mode !== s.mode;
      window.setTimeout(() => setReady(s.id), (s.enter ? 450 : 0) + (moved ? 700 : 0));
    }, 150);
    return () => window.clearTimeout(k);
  }, [step, mode, id, fresh]);

  // the body may count what is on screen (the timeline's window): keep it current
  useEffect(() => {
    const k = window.setInterval(() => setTick((n) => n + 1), 500);
    return () => window.clearInterval(k);
  }, []);

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
  return (
    <Mask key={step.id} step={step} ctx={ctx} h={h} phase={phase} shown={ready === step.id} nav={nav.current} onNext={() => void ok()} onExit={() => void exit()} />
  );
}

type Phase = "read" | "act" | "result" | "nav" | "going";

/** The link LACUNA clicks to get to the next step's page: 下一步 when it goes there, else the page's own tab. */
function navLink(id: string, mode: string): HTMLElement | null {
  const href = `#/ep/${encodeURIComponent(id)}/${mode}`;
  const next = document.querySelector<HTMLElement>('[data-testid="next-step"]');
  if (next?.getAttribute("href") === href) return next;
  return [...document.querySelectorAll<HTMLElement>(`a[href="${href}"]`)].find((a) => !!visible(a)) ?? null;
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

function Mask({ step, ctx, h, phase, shown, nav, onNext, onExit }: {
  step: Step;
  ctx: React.MutableRefObject<Ctx>;
  h: Hosts;
  phase: Phase;
  shown: boolean;
  nav: HTMLElement | null;
  onNext: () => void;
  onExit: () => void;
}) {
  const going = (phase === "nav" || phase === "going") && !!nav;
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
      const els = going && nav ? [nav] : elements(step, c);
      const rs = els.map(visible).filter((r): r is DOMRect => !!r);
      if (!scrolled.current && els.length && rs.length) {
        scrolled.current = true;
        const r = rs[0];
        if (r.top < 70 || r.bottom > window.innerHeight - 10) els[0].scrollIntoView({ block: "center" });
      }
      const nh = union(rs);
      setHole((o) => (same(o, nh) ? o : nh));
      // the dashed box on the timeline
      const bx = going ? null : (step.box?.(c) ?? null);
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
  }, [step, ctx, going, nav]);

  useLayoutEffect(() => {
    const b = bubble.current;
    if (!b) return;
    const near = step.around?.map((sel) => document.querySelector(sel)).filter((e): e is Element => !!e).map((e) => e.getBoundingClientRect()) ?? [];
    const p = place(near.length ? union([...(hole ? [new DOMRect(hole.x, hole.y, hole.w, hole.h)] : []), ...near]) : hole, { w: b.offsetWidth, h: b.offsetHeight }, step.side);
    setPos((o) => (o && Math.abs(o.left - p.left) < 0.5 && Math.abs(o.top - p.top) < 0.5 ? o : p));
  });

  const all = STEPS.filter((s) => s.ch === step.ch);
  const k = all.indexOf(step) + 1;
  const acting = phase === "act" || phase === "going";
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
    <div className="tour" data-testid="tour" data-step={step.id} data-phase={phase} onPointerDown={stop} onMouseDown={stop}>
      {shades.map((r, i) => (
        <div key={i} className="tour-shade" style={{ left: r.x, top: r.y, width: r.w, height: r.h }} />
      ))}
      {hole && <div className={`tour-ring${acting ? " is-acting" : ""}`} style={{ left: hole.x, top: hole.y, width: hole.w, height: hole.h }} />}
      {hole && <div className="tour-block" style={{ left: hole.x, top: hole.y, width: hole.w, height: hole.h }} />}
      {box && <div className="tour-box" style={{ left: box.x, top: box.y, width: box.w, height: box.h }} data-testid="tour-box" />}
      <Pill ch={step.ch} onExit={onExit} />
      <div
        ref={bubble}
        className="tour-bubble"
        role="dialog"
        aria-label={step.title(h)}
        style={pos && shown ? { left: pos.left, top: pos.top } : { visibility: "hidden" }}
        data-testid="tour-bubble"
      >
        <span className="tour-meta">
          {t("第 {n} 步，共 {total} 步", { n: step.ch, total: CHAPTERS })} · {chapterName(step.ch)} · {k}/{all.length}
        </span>
        <h3>{going ? t("这一部分看完了") : step.title(h)}</h3>
        {phase === "read" && <p>{rich(step.body(h, ctx.current))}</p>}
        {phase === "result" && <p>{rich(step.result?.(h) ?? "")}</p>}
        {going && <p>{rich(t("按 **知道了**，LACUNA 点 **{label}**，进入下一部分。", { label: (nav?.textContent ?? "").trim() }))}</p>}
        <div className="tour-foot">
          {acting ? (
            <span className="tour-hint" data-testid="tour-acting">
              {going ? t("正在打开…") : (step.hint?.(h) ?? t("LACUNA 正在操作…"))}
            </span>
          ) : (
            <button type="button" className="btn btn-primary btn-small" onClick={onNext} data-testid="tour-ok" autoFocus>
              {t("知道了")}
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
  // read first; after 知道了 LACUNA plays it; when it ends (or is paused from the pill), the result
  const [phase, setPhase] = useState<"read" | "act" | "result">("read");
  const [now, setNow] = useState(0);
  const audio = useRef<HTMLAudioElement>(null);
  const play = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    req<AB>("GET", `/api/episodes/${encodeURIComponent(id)}/tour/raw`).then(setAb, () => undefined);
  }, [id]);
  const ok = async () => {
    if (phase === "result") return onNext();
    if (phase !== "read" || !audio.current) return;
    setPhase("act");
    await tap(play.current, 900);
    void audio.current.play().catch(() => setPhase("result"));
  };
  return (
    <div className="tour" data-testid="tour" data-step={step.id} data-phase={phase}>
      <div className="tour-shade" style={{ inset: 0 }} />
      <Pill ch={1} onExit={onExit} />
      <div className="tour-modal card" role="dialog" aria-label={step.title(h)} data-testid="tour-raw">
        <span className="tour-meta">{t("第 {n} 步，共 {total} 步", { n: 1, total: CHAPTERS })} · {chapterName(1)}</span>
        <h2>{step.title(h)}</h2>
        <p>{rich(phase === "result" ? (step.result?.(h) ?? "") : step.body(h))}</p>
        <div className="tour-play">
          <button ref={play} type="button" className="btn btn-primary" tabIndex={-1} disabled={!ab} data-testid="tour-raw-play">
            {phase === "act" ? t("❚❚ 正在播放") : t("▶ 播放原始录音")}
          </button>
          <span className="mono small">
            {fmt(now)} / {fmt(ab?.before.duration ?? 30)}
          </span>
        </div>
        <audio
          ref={audio}
          src={ab?.before.url}
          onPause={() => setPhase((p) => (p === "act" ? "result" : p))}
          onTimeUpdate={(e) => setNow(e.currentTarget.currentTime)}
          data-testid="tour-raw-audio"
        />
        <div className="tour-foot">
          {phase === "act" ? (
            <span className="tour-hint" data-testid="tour-acting">{t("正在播放原始录音…")}</span>
          ) : (
            <button type="button" className="btn btn-primary btn-small" onClick={() => void ok()} disabled={!ab} data-testid="tour-ok" autoFocus>
              {t("知道了")}
            </button>
          )}
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
      t("审阅了 {n} 处", { n: reviewed }),
      t("手动剪了 {n} 处", { n: manual }),
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
          <button type="button" className="btn btn-outline" onClick={() => void leave(() => (window.location.hash = `#/ep/${encodeURIComponent(id)}/listen`))} data-testid="tour-try">
            {t("自己在示例里试试")}
          </button>
        </div>
        <p className="small muted">{t("示例节目会留在你的节目列表里，可以随便点；不想要了在 设置 → 通用 里删除。")}</p>
      </div>
    </div>
  );
}
