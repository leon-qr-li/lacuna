import { Fragment, useCallback, useEffect, useState } from "react";
import type { EditInfo, Episode } from "./api";
import { api } from "./api";
import { ChatPanel } from "./components/ChatPanel";
import { Icon } from "./components/Icon";
import { NearbyEdits } from "./components/NearbyEdits";
import { PlayerBar } from "./components/PlayerBar";
import { ReviewView } from "./components/ReviewView";
import { Lanes, Overview } from "./components/Timeline";
import { navLinks, pages, tabs } from "./features/registry";
import type { NavLink } from "./features/registry";
import { usePlayer } from "./usePlayer";
import { MusicListenToggle, useMusicListen } from "./features/library/useMusicListen";
import { t } from "./i18n";
import { PageLoading } from "./features/loading/Loading";
import { Home } from "./features/episodes/Home";

// 整集试听 and 改动审阅 are built in; the other tabs come from src/features/*/index.tsx
type Mode = string;

function parseHash(): { id: string | null; mode: Mode; page: string | null } {
  const m = /^#\/ep\/([^/]+)(?:\/([\w-]+))?/.exec(window.location.hash);
  const mode = m?.[2] && (m[2] === "review" || tabs.some((t) => t.mode === m[2])) ? m[2] : "listen";
  const p = /^#\/([\w-]+)/.exec(window.location.hash)?.[1] ?? null;
  return {
    id: m ? decodeURIComponent(m[1]) : null,
    mode,
    page: p && pages.some((x) => x.path === p) ? p : null,
  };
}

function useRoute() {
  const [route, setRoute] = useState(parseHash);
  useEffect(() => {
    const on = () => setRoute(parseHash());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

/** Labels of tab groups in the episode flow (see EpisodeTab.group). */
const GROUPS: Record<string, string> = { publish: t("发布") };

const readPref = (k: string) => {
  try {
    return localStorage.getItem(k);
  } catch {
    return null;
  }
};
const writePref = (k: string, v: string) => {
  try {
    localStorage.setItem(k, v);
  } catch {
    /* private mode */
  }
};

export default function App() {
  const { id, mode, page } = useRoute();
  if (page) return <PageScreen path={page} />;
  return id ? <EpisodeScreen key={id} id={id} mode={mode} /> : <Home nav={<Nav on="home" />} />;
}

function Nav({ on, except }: { on: NavLink["on"][number]; except?: string }) {
  return (
    <>
      {navLinks
        .filter((l) => l.on.includes(on) && l.path !== except)
        .map((l) => (
          <Fragment key={l.path}>{l.render()}</Fragment>
        ))}
    </>
  );
}

function PageScreen({ path }: { path: string }) {
  const page = pages.find((p) => p.path === path)!;
  return (
    <div className="app">
      <header className="topbar">
        <a className="brand" href="#/">
          LACUNA
        </a>
        <span className="crumb-sep" aria-hidden="true">
          /
        </span>
        <span className="ep-title">{page.title}</span>
        <span className="grow" />
        <Nav on="page" except={path} />
      </header>
      {page.render()}
    </div>
  );
}

function EpisodeScreen({ id, mode }: { id: string; mode: Mode }) {
  const [ep, setEp] = useState<Episode | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const raw = usePlayer();
  const listen = useMusicListen(id, `${ep?.version ?? ""}|${mode}`, raw);
  const player = listen.player; // voice-cut time, also while listening with music
  const [chatOpen, setChatOpen] = useState(() => readPref("lacuna.chat") !== "closed");
  useEffect(() => writePref("lacuna.chat", chatOpen ? "open" : "closed"), [chatOpen]);

  useEffect(() => {
    api.episode(id).then(setEp).catch((e) => setErr(String(e.message ?? e)));
  }, [id]);

  // new edit version -> swap the stream, keeping the (server-mapped) position
  useEffect(() => {
    if (ep) player.load(ep.audio_url, ep.playhead ?? player.time);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ep?.audio_url, ep?.playhead]);

  const flash = (msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast((t) => (t === msg ? null : t)), 2500);
  };

  const run = useCallback(
    async (p: Promise<Episode>, msg?: string | ((next: Episode) => string)): Promise<boolean> => {
      try {
        const next = await p;
        setEp(next);
        if (msg) flash(typeof msg === "function" ? msg(next) : msg);
        return true;
      } catch (e) {
        flash(t("操作失败：{message}", { message: (e as Error).message }));
        return false;
      }
    },
    [],
  );

  const undo = () => ep?.can_undo && run(api.undo(id, player.time), t("已撤销：{undo_label}", { undo_label: ep.undo_label }));
  const redo = () => ep?.can_redo && run(api.redo(id, player.time), t("已重做：{redo_label}", { redo_label: ep.redo_label }));
  const review = (e: EditInfo, action: "keep" | "restore" | "apply") =>
    run(
      api.review(id, e.id, action, player.time),
      action === "restore" ? (e.status === "restored" ? t("已确认不删") : t("已恢复原话")) : action === "keep" ? t("已保留") : t("已重新应用"),
    );
  const approveAll = () =>
    run(api.reviewAll(id, "approve", player.time), (n) => t("已全部通过 {changed} 处，可撤销", { changed: (n as Episode & { changed: number }).changed }));

  // global keys: space play/pause and arrows (listen mode), ctrl/cmd+z undo
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      const typing = tag === "INPUT" || tag === "TEXTAREA";
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z" && !typing) {
        e.preventDefault();
        void (e.shiftKey ? redo() : undo());
        return;
      }
      if (typing || mode !== "listen" || e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key === " " && tag !== "BUTTON") {
        e.preventDefault();
        player.toggle();
      } else if (e.key === "ArrowLeft") player.skip(-5);
      else if (e.key === "ArrowRight") player.skip(5);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (err) return <p className="error pad">{t("无法打开剧集：")}{err}</p>;

  const pending = ep?.proposals[0]?.edit ?? null;
  const href = (m: Mode) => `#/ep/${encodeURIComponent(id)}/${m}`;
  // the episode flow: built-in steps, then feature tabs; a tab group (发布) is one step with sub-tabs
  const curGroup = tabs.find((t) => t.mode === mode)?.group;
  const steps: { mode: Mode; label: string; on: boolean; badge?: number }[] = [
    { mode: "review", label: t("审阅改动"), on: mode === "review", badge: ep?.pending_review ?? 0 },
    { mode: "listen", label: t("整集试听"), on: mode === "listen" },
  ];
  for (const t of tabs) {
    if (!t.group) steps.push({ mode: t.mode, label: t.label, on: mode === t.mode });
    else if (!steps.some((x) => x.mode === t.group))
      steps.push({ mode: t.group, label: GROUPS[t.group] ?? t.group, on: curGroup === t.group });
  }
  const stepHref = (m: Mode) => href(tabs.find((t) => t.group === m)?.mode ?? m);
  // every page in flow order (groups expanded), for the "下一步" button at the bottom
  const flow = steps.flatMap((x) =>
    GROUPS[x.mode] ? tabs.filter((t) => t.group === x.mode).map((t) => ({ mode: t.mode, label: t.label })) : [x],
  );
  const next = flow[flow.findIndex((x) => x.mode === mode) + 1];
  return (
    <div className="app">
      <header className="topbar">
        <a className="brand" href="#/">
          LACUNA
        </a>
        <span className="crumb-sep" aria-hidden="true">
          /
        </span>
        <span className="ep-title">{ep?.title ?? "…"}</span>
        <span className="grow" />
        <Nav on="episode" />
        {mode === "listen" && (
          <button
            type="button"
            className={`btn btn-small ${chatOpen ? "btn-outline" : "btn-grad"}`}
            aria-pressed={chatOpen}
            onClick={() => setChatOpen((o) => !o)}
            data-testid="chat-toggle"
          >
            <Icon name="chat" /> {chatOpen ? t("收起 AI 制作人") : t("AI 制作人")}
          </button>
        )}
      </header>
      <div className="ep-head">
        <div className="ep-head-row">
          {ep && (
            <span className="chip">
              {ep.demo ? t("第一刀（演示）已完成 · {n} 处待你过目", { n: ep.pending_review }) : t("第一刀已完成 · {n} 处待你过目", { n: ep.pending_review })}
            </span>
          )}
          <span className="grow" />
          <button type="button" className="btn btn-ghost btn-small" onClick={undo} disabled={!ep?.can_undo} title={ep?.undo_label ?? ""}>
            <Icon name="undo" /> {t("撤销")}
          </button>
          <button type="button" className="btn btn-ghost btn-small" onClick={redo} disabled={!ep?.can_redo} title={ep?.redo_label ?? ""}>
            <Icon name="redo" /> {t("重做")}
          </button>
          {mode !== "export" && (
            <a className="btn btn-primary btn-small linkbtn" href={href("export")} data-testid="export-toggle">
              {t("导出")}
            </a>
          )}
        </div>
        <nav aria-label={t("制作流程")} className="modes">
          {steps.map((s, i) => (
            <Fragment key={s.mode}>
              {i > 0 && (
                <span className="mode-sep">
                  <Icon name="chev" size={14} />
                </span>
              )}
              <a href={stepHref(s.mode)} aria-current={s.on ? "page" : undefined}>
                {s.label}
                {s.badge !== undefined && <span className={`mode-badge ${s.badge ? "" : "is-zero"}`}> · {s.badge}</span>}
              </a>
            </Fragment>
          ))}
        </nav>
        {curGroup && (
          <nav aria-label={GROUPS[curGroup] ?? curGroup} className="subtabs">
            {tabs
              .filter((t) => t.group === curGroup)
              .map((t) => (
                <a key={t.mode} href={href(t.mode)} aria-current={mode === t.mode ? "page" : undefined}>
                  {t.label}
                </a>
              ))}
          </nav>
        )}
      </div>
      {ep?.demo && <p className="banner">{ep.demo_note || t("演示数据")}</p>}
      {toast && (
        <div className="toast" role="status">
          {toast}
        </div>
      )}
      {/* one audio element shared by both modes: the playhead is common */}
      <audio ref={raw.ref} preload="auto" data-testid="main-audio" />
      {!ep ? (
        <PageLoading label={t("正在打开这一集…")} shape="episode" />
      ) : (
        <>
          {/* Full Listen stays mounted in review mode so the conversation is kept */}
          <div className={`workspace ${chatOpen ? "" : "chat-closed"}`} hidden={mode !== "listen"}>
            <ChatPanel ep={ep} time={player.time} onEpisode={setEp} onPauseMain={player.pause} />
            <main className="center">
              <Overview ep={ep} time={player.time} onSeek={player.seek} />
              <Lanes ep={ep} time={player.time} onSeek={player.seek} highlight={pending} />
              <PlayerBar player={player} duration={ep.duration} />
              <MusicListenToggle listen={listen} />
              <NearbyEdits ep={ep} time={player.time} onSeek={player.seek} onReview={review} />
            </main>
          </div>
          {mode === "review" && (
            <ReviewView
              ep={ep}
              selected={selected}
              onSelect={(e) => {
                setSelected(e.id);
                player.seek(e.t); // keep the shared playhead on the edit under review
              }}
              onReview={review}
              onApproveAll={approveAll}
              onPauseMain={player.pause}
            />
          )}
          {tabs
            .filter((t) => t.mode === mode)
            .map((t) => (
              <Fragment key={t.mode}>{t.render({ id, ep, flash, pauseMain: player.pause })}</Fragment>
            ))}
          {next && (
            <div className="next-step">
              <span className="muted small">{t("这一步做完了？")}</span>
              <a className="btn linkbtn" href={href(next.mode)}>
                {t("下一步：")}{next.label} <Icon name="chev" />
              </a>
            </div>
          )}
        </>
      )}
    </div>
  );
}
