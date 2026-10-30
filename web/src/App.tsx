import { Fragment, useCallback, useEffect, useState } from "react";
import type { EditInfo, Episode, RequestError } from "./api";
import { api } from "./api";
import { ChatPanel } from "./components/ChatPanel";
import { ChatFab } from "./features/chat-dock/ChatDock";
import { Tour } from "./features/tour/Tour";
import { Icon } from "./components/Icon";
import { NearbyEdits, nearEdits } from "./components/NearbyEdits";
import { PlayerBar } from "./components/PlayerBar";
import { ReviewView } from "./components/ReviewView";
import { EditLanes } from "./features/manual/EditLanes";
import { TranscriptEdit } from "./features/manual/TranscriptEdit";
import { usePositions } from "./features/positions/usePositions";
import { useManual } from "./features/manual/useManual";
import { navLinks, pages, tabs as allTabs } from "./features/registry";
import { useShow } from "./features/show/api";
import { MissingSources } from "./features/sources/MissingSources";
import type { NavLink } from "./features/registry";
import { usePlayer } from "./usePlayer";
import { MusicListenToggle, useMusicListen } from "./features/library/useMusicListen";
import { t } from "./i18n";
import { PageLoading } from "./features/loading/Loading";
import { ErrorState } from "./features/states/States";
import { openEpisode, type Restoring } from "./features/cold/restore";
import { Home } from "./features/episodes/Home";
import { FirstShow } from "./features/first-show/FirstShow";
import { useProjects } from "./features/projects/api";
import { ProjectCrumb } from "./features/projects/ProjectMenu";
import { Presence } from "./features/coedit/Presence";
import { useCoedit } from "./features/coedit/useCoedit";
import { CutPop, NextStep, SideTabs, readSideTab, writeSideTab } from "./features/workbench/Workbench";
import type { SideTab } from "./features/workbench/Workbench";
import { MenuNav } from "./features/mobile/MenuNav";

// 整集试听 and 改动审阅 are built in; the other tabs come from src/features/*/index.tsx
type Mode = string;

function parseHash(): { id: string | null; mode: Mode; page: string | null } {
  const m = /^#\/ep\/([^/]+)(?:\/([\w-]+))?/.exec(window.location.hash);
  const mode = m?.[2] && (m[2] === "review" || allTabs.some((t) => t.mode === m[2])) ? m[2] : "listen";
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
  // in no show at all: every show page would be refused, so make the first one (settings still opens)
  const sp = useProjects();
  if (sp && !sp.current && page !== "settings") return <FirstShow />;
  if (page) return <PageScreen path={page} />;
  return id ? <EpisodeScreen key={id} id={id} mode={mode} /> : <Home nav={<Nav on="home" />} />;
}

function Nav({ on }: { on: NavLink["on"][number] }) {
  return (
    <MenuNav>
      {navLinks
        .filter((l) => l.on.includes(on))
        .map((l) => (
          <Fragment key={l.path}>{l.render()}</Fragment>
        ))}
    </MenuNav>
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
        <ProjectCrumb />
        <span className="crumb-sep" aria-hidden="true">
          /
        </span>
        <span className="ep-title">{page.title}</span>
        <span className="grow" />
        <Nav on="page" />
      </header>
      {page.render()}
    </div>
  );
}

function EpisodeScreen({ id, mode }: { id: string; mode: Mode }) {
  const [ep, setEp] = useState<Episode | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [attempt, setAttempt] = useState(0);
  // a toast; `undo` puts a small 撤销 button in it (after a bulk action: 全部通过 / 去掉 um/uh / 统一音量)
  const [toast, setToast] = useState<{ msg: string; undo?: boolean } | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const raw = usePlayer();
  const listen = useMusicListen(id, `${ep?.version ?? ""}|${mode}`, raw);
  const player = listen.player; // voice-cut time, also while listening with music
  // narrower than 1280 the panel starts closed, so the editor has the room (batch 7, B26); only a click is remembered
  const [chatOpen, setChatOpenRaw] = useState(() => window.innerWidth >= 1280 && readPref("lacuna.chat") !== "closed");
  const setChatOpen = (v: boolean) => {
    setChatOpenRaw(v);
    writePref("lacuna.chat", v ? "open" : "closed");
  };
  const [sideTab, setSideTab] = useState<SideTab>(readSideTab);
  useEffect(() => writeSideTab(sideTab), [sideTab]);

  // an episode not opened for a while: its audio comes back from cloud storage first (features/cold)
  const [restoring, setRestoring] = useState<Restoring | null>(null);
  useEffect(() => {
    let alive = true;
    setErr(null);
    openEpisode(() => api.episode(id), setRestoring, () => alive)
      .then((e) => alive && setEp(e))
      .catch((e) => alive && setErr(e ?? new Error("")))
      .finally(() => alive && setRestoring(null));
    return () => {
      alive = false;
    };
  }, [id, attempt]);

  const positions = usePositions(id, mode, player); // each page's own place, kept across refreshes (features/positions)
  // new edit version -> swap the stream, keeping the (server-mapped) position
  useEffect(() => {
    if (ep) player.load(ep.audio_url, ep.playhead ?? positions.resume() ?? player.time);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ep?.audio_url, ep?.playhead]);

  const flash = (msg: string, opts?: { undo?: boolean }) => {
    const item = { msg, undo: opts?.undo };
    setToast(item);
    window.setTimeout(() => setToast((t) => (t === item ? null : t)), opts?.undo ? 6000 : 2500);
  };

  const run = useCallback(
    async (p: Promise<Episode>, msg?: string | ((next: Episode) => string), opts?: { undo?: boolean }): Promise<boolean> => {
      try {
        const next = await p;
        setEp(next);
        if (msg) flash(typeof msg === "function" ? msg(next) : msg, opts);
        return true;
      } catch (e) {
        if ((e as RequestError).stale) {
          // someone else changed it first (features/coedit): show the latest, say why nothing happened
          api.episode(id).then(setEp, () => undefined);
          flash((e as Error).message);
          return false;
        }
        flash(t("操作失败：{message}", { message: (e as Error).message }));
        // the answer may be what was lost, not the change (Leon 2026-10-30: 删除这段 hung, and after a refresh
        // the word was gone): show what the server has now
        api.episode(id).then(setEp, () => undefined);
        return false;
      }
    },
    [id],
  );
  const { others } = useCoedit(id, ep, setEp, flash);
  const show = useShow();

  const undo = () => {
    setToast(null);
    return ep?.can_undo && run(api.undo(id, player.time), t("已撤销：{undo_label}", { undo_label: ep.undo_label }));
  };
  const redo = () => ep?.can_redo && run(api.redo(id, player.time), t("已重做：{redo_label}", { redo_label: ep.redo_label }));
  const review = (e: EditInfo, action: "keep" | "restore" | "apply") =>
    run(
      api.review(id, e.id, action, player.time, ep?.rev),
      action === "restore" ? (e.status === "restored" ? t("已确认不删") : t("已恢复原话")) : action === "keep" ? t("已保留") : t("已重新应用"),
    );
  const approveAll = () =>
    run(
      api.reviewAll(id, "approve", player.time, undefined, ep?.rev),
      (n) => t("已全部通过 {changed} 处，Ctrl+Z 可撤销", { changed: (n as Episode & { changed: number }).changed, n: (n as Episode & { changed: number }).changed }),
      { undo: true },
    );

  const manual = useManual(ep, player, run); // the selection of 手动剪辑 (timeline + transcript)

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

  if (err)
    return (
      <div className="app">
        <header className="topbar">
          <a className="brand" href="#/">
            LACUNA
          </a>
          <ProjectCrumb />
          <span className="grow" />
          <Nav on="episode" />
        </header>
        <ErrorState
          title={t("这一集打不开")}
          error={err}
          onRetry={() => setAttempt((n) => n + 1)}
          back={{ href: "#/", label: t("回首页") }}
        />
      </div>
    );

  const pending = ep?.proposals[0]?.edit ?? null;
  const href = (m: Mode) => `#/ep/${encodeURIComponent(id)}/${m}`;
  // the episode flow: built-in steps, then feature tabs; a tab group (发布) is one step with sub-tabs
  const tabs = allTabs.filter((x) => !x.visible || x.visible(show));
  const curGroup = tabs.find((t) => t.mode === mode)?.group;
  const steps: { mode: Mode; label: string; on: boolean; badge?: number }[] = [
    { mode: "review", label: t("审阅改动"), on: mode === "review", badge: ep?.pending_review ?? 0 },
    { mode: "listen", label: t("整集试听"), on: mode === "listen" },
  ];
  for (const t of tabs) {
    if (t.offFlow) continue;
    if (!t.group) steps.push({ mode: t.mode, label: t.label, on: mode === t.mode });
    else if (!steps.some((x) => x.mode === t.group))
      steps.push({ mode: t.group, label: GROUPS[t.group] ?? t.group, on: curGroup === t.group });
  }
  const stepHref = (m: Mode) => href(tabs.find((t) => t.group === m)?.mode ?? m);
  // every page in flow order (groups expanded), for the "下一步" button at the top right
  const flow = steps.flatMap((x) =>
    GROUPS[x.mode] ? tabs.filter((t) => t.group === x.mode).map((t) => ({ mode: t.mode, label: t.label })) : [x],
  );
  const next = flow[flow.findIndex((x) => x.mode === mode) + 1];
  return (
    <div className={`app ${ep && mode === "listen" ? "wb-fit" : ""}`}>
      <header className="topbar">
        <a className="brand" href="#/">
          LACUNA
        </a>
        <ProjectCrumb />
        <span className="crumb-sep" aria-hidden="true">
          /
        </span>
        <span className="ep-title">{ep?.title ?? "…"}</span>
        <span className="grow" />
        <Nav on="episode" />
      </header>
      <div className="ep-head">
        <div className="ep-head-row">
          <div className="ep-head-side">
            {ep && mode === "listen" && (
              <a className="small muted ep-lessons-link" href={href("lessons")} data-testid="lessons-link">
                {t("这一集 LACUNA 学到了什么？")}
              </a>
            )}
            <Presence others={others} />
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
          {/* the slot stays when there is no next page, so the step bar never moves (batch 7, T1) */}
          <div className="ep-head-side ep-head-end">{next && <NextStep href={href(next.mode)} label={next.label} />}</div>
        </div>
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
      {ep && <MissingSources ep={ep} />}
      {toast && (
        <div className={`toast ${toast.undo ? "toast-undo" : ""}`} role="status">
          {toast.msg}
          {toast.undo && ep?.can_undo && (
            <button type="button" className="toast-undo-btn" onClick={() => void undo()} data-testid="toast-undo">
              {t("撤销")}
            </button>
          )}
        </div>
      )}
      {ep && <Tour ep={ep} mode={mode} id={id} player={player} />}
      {/* one audio element shared by both modes: the playhead is common */}
      <audio ref={raw.ref} preload="auto" data-testid="main-audio" />
      {!ep ? (
        restoring ? (
          <div className="cold-restoring" data-testid="audio-restoring">
            <PageLoading label={t("正在取回这一集的音频… {p}%", { p: Math.round(restoring.progress * 100) })} shape="episode" />
            <p className="muted pad">{t("这一集很久没打开了，音频放在云端，取回来大约要 10–30 秒。")}</p>
          </div>
        ) : (
          <PageLoading label={t("正在打开这一集…")} shape="episode" />
        )
      ) : (
        <>
          {/* Full Listen stays mounted in review mode so the conversation is kept */}
          {/* one screen (features/workbench): timeline + transcript, side panel tabs AI 制作人 / 这附近改了什么 */}
          <div className={`workspace wb ${chatOpen ? "" : "chat-closed"}`} hidden={mode !== "listen"}>
            <ChatPanel
              ep={ep}
              time={player.time}
              onEpisode={setEp}
              onPauseMain={player.pause}
              onCollapse={() => setChatOpen(false)}
              tabs={(badge) => <SideTabs tab={sideTab} onTab={setSideTab} near={nearEdits(ep, player.time).length} badge={badge} />}
              alt={
                sideTab === "near" ? (
                  <div className="side-near" role="tabpanel">
                    <NearbyEdits ep={ep} time={player.time} onSeek={player.seek} onReview={review} />
                  </div>
                ) : null
              }
            />
            {!chatOpen && mode === "listen" && <ChatFab onClick={() => setChatOpen(true)} />}
            <main className="center">
              <EditLanes
                ep={ep}
                time={player.time}
                player={player}
                highlight={pending}
                m={manual}
                bottom={
                  <>
                    <PlayerBar player={player} duration={ep.duration} />
                    <MusicListenToggle listen={listen} />
                  </>
                }
                popover={(e) => (
                  <CutPop
                    e={e}
                    onListen={() => {
                      player.seek(Math.max(0, e.t - 3));
                      player.play();
                    }}
                    onReview={review}
                  />
                )}
              />
              <TranscriptEdit ep={ep} time={player.time} player={player} m={manual} run={run} />
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
              <Fragment key={t.mode}>{t.render({ id, ep, flash, pauseMain: player.pause, onEpisode: setEp })}</Fragment>
            ))}
        </>
      )}
    </div>
  );
}
