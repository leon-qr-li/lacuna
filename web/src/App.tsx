import { useCallback, useEffect, useState } from "react";
import type { EditInfo, Episode, EpisodeListItem } from "./api";
import { api, fmt } from "./api";
import { ChatPanel } from "./components/ChatPanel";
import { NearbyEdits } from "./components/NearbyEdits";
import { PlayerBar } from "./components/PlayerBar";
import { ReviewView } from "./components/ReviewView";
import { Lanes, Overview } from "./components/Timeline";
import { usePlayer } from "./usePlayer";

type Mode = "listen" | "review";

function parseHash(): { id: string | null; mode: Mode } {
  const m = /^#\/ep\/([^/]+)(?:\/(listen|review))?/.exec(window.location.hash);
  return { id: m ? decodeURIComponent(m[1]) : null, mode: (m?.[2] as Mode) ?? "listen" };
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

const go = (id: string, mode: Mode = "listen") => {
  window.location.hash = `#/ep/${encodeURIComponent(id)}/${mode}`;
};

export default function App() {
  const { id, mode } = useRoute();
  return id ? <EpisodeScreen key={id} id={id} mode={mode} /> : <Home />;
}

function Home() {
  const [list, setList] = useState<EpisodeListItem[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    api
      .episodes()
      .then((r) => {
        setList(r.episodes);
        if (r.episodes.length === 1 && !r.episodes[0].error) go(r.episodes[0].id);
      })
      .catch((e) => setErr(String(e)));
  }, []);
  return (
    <div className="app">
      <header className="topbar">
        <strong className="brand">LACUNA</strong>
      </header>
      <main className="home">
        <h1>剧集</h1>
        {err && <p className="error">{err}</p>}
        {list?.length === 0 && <p className="muted">工作区里还没有剧集。用 scripts/make_demo_episode.py 建一个演示集。</p>}
        <ul className="ep-list">
          {list?.map((e) => (
            <li key={e.id}>
              <a href={`#/ep/${encodeURIComponent(e.id)}/listen`}>
                <strong>{e.title}</strong>
                {e.error ? (
                  <span className="error small">无法打开：{e.error}</span>
                ) : (
                  <span className="muted small">
                    {fmt(e.raw_duration ?? 0)} → {fmt(e.duration ?? 0)} · {e.pending_review} 处待过目
                    {e.demo && " · 演示数据"}
                  </span>
                )}
              </a>
            </li>
          ))}
        </ul>
      </main>
    </div>
  );
}

function EpisodeScreen({ id, mode }: { id: string; mode: Mode }) {
  const [ep, setEp] = useState<Episode | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const player = usePlayer();

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
    async (p: Promise<Episode>, msg?: string) => {
      try {
        const next = await p;
        setEp(next);
        if (msg) flash(msg);
      } catch (e) {
        flash(`操作失败：${(e as Error).message}`);
      }
    },
    [],
  );

  const undo = () => ep?.can_undo && run(api.undo(id, player.time), `已撤销：${ep.undo_label}`);
  const redo = () => ep?.can_redo && run(api.redo(id, player.time), `已重做：${ep.redo_label}`);
  const review = (e: EditInfo, action: "keep" | "restore" | "apply") =>
    run(api.review(id, e.id, action, player.time), action === "restore" ? "已恢复原话" : action === "keep" ? "已保留" : "已重新应用");

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

  if (err) return <p className="error pad">无法打开剧集：{err}</p>;

  const pending = ep?.proposals[0]?.edit ?? null;
  return (
    <div className="app">
      <header className="topbar">
        <a className="brand" href="#/">
          LACUNA
        </a>
        <span className="muted">/</span>
        <span className="ep-title">{ep?.title ?? "…"}</span>
        {ep && (
          <span className="chip">
            第一刀{ep.demo ? "（演示）" : ""}已完成 · {ep.pending_review} 处待你过目
          </span>
        )}
        <nav aria-label="审阅模式" className="modes">
          <a href={`#/ep/${encodeURIComponent(id)}/listen`} aria-current={mode === "listen" ? "page" : undefined}>
            整集试听
          </a>
          <a href={`#/ep/${encodeURIComponent(id)}/review`} aria-current={mode === "review" ? "page" : undefined}>
            改动审阅 · {ep?.pending_review ?? 0}
          </a>
        </nav>
        <div className="row gap8">
          <button type="button" className="btn btn-outline" onClick={undo} disabled={!ep?.can_undo} title={ep?.undo_label ?? ""}>
            撤销
          </button>
          <button type="button" className="btn btn-outline" onClick={redo} disabled={!ep?.can_redo} title={ep?.redo_label ?? ""}>
            重做
          </button>
        </div>
      </header>
      {ep?.demo && <p className="banner">{ep.demo_note || "演示数据"}</p>}
      {toast && (
        <div className="toast" role="status">
          {toast}
        </div>
      )}
      {/* one audio element shared by both modes: the playhead is common */}
      <audio ref={player.ref} preload="auto" data-testid="main-audio" />
      {!ep ? (
        <p className="pad muted">加载中…</p>
      ) : mode === "listen" ? (
        <div className="workspace">
          <ChatPanel ep={ep} time={player.time} onEpisode={setEp} onPauseMain={player.pause} />
          <main className="center">
            <Overview ep={ep} time={player.time} onSeek={player.seek} />
            <Lanes ep={ep} time={player.time} onSeek={player.seek} highlight={pending} />
            <PlayerBar player={player} duration={ep.duration} />
            <NearbyEdits ep={ep} time={player.time} onSeek={player.seek} onReview={review} />
          </main>
        </div>
      ) : (
        <ReviewView
          ep={ep}
          selected={selected}
          onSelect={(e) => {
            setSelected(e.id);
            player.seek(e.t); // keep the shared playhead on the edit under review
          }}
          onReview={review}
          onPauseMain={player.pause}
        />
      )}
    </div>
  );
}
