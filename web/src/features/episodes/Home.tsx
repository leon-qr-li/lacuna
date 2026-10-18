import { useCallback, useEffect, useState, type ReactNode } from "react";
import type { EpisodeListItem } from "../../api";
import { api } from "../../api";
import { t } from "../../i18n";
import { EpisodeListSkeleton } from "../loading/Loading";
import { ImportPanel } from "../import/ImportPanel";
import { EpisodeCard } from "./EpisodeCard";
import { episodesApi } from "./api";

const go = (id: string, mode = "listen") => {
  window.location.hash = `#/ep/${encodeURIComponent(id)}/${mode}`;
};

/** 剧集: the import panel and every episode that isn't archived (首检 #3: archived ones are on #/archive).
 *  `nav` = the top-bar links (App.tsx). */
export function Home({ nav }: { nav: ReactNode }) {
  const [list, setList] = useState<EpisodeListItem[] | null>(null);
  const [archived, setArchived] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const [undo, setUndo] = useState<EpisodeListItem | null>(null);
  const load = useCallback((first = false) => {
    Promise.all([episodesApi.episodes(), api.imports().catch(() => ({ jobs: [] }))])
      .then(([r, im]) => {
        setList(r.episodes);
        setArchived(r.archived ?? 0);
        // opening the app with a single episode and nothing importing: go straight to it
        // (not when Leon came back here on purpose via the LACUNA link)
        if (first && !window.location.hash && r.episodes.length === 1 && !r.episodes[0].error && !im.jobs.length)
          go(r.episodes[0].id);
      })
      .catch((e) => setErr(String(e)));
  }, []);
  useEffect(() => load(true), [load]);
  useEffect(() => {
    if (!undo) return;
    const timer = window.setTimeout(() => setUndo(null), 8000);
    return () => window.clearTimeout(timer);
  }, [undo]);
  const reload = useCallback(() => load(), [load]);
  const open = useCallback((id: string) => go(id, "review"), []);
  const archive = (e: EpisodeListItem) =>
    episodesApi
      .archive(e.id)
      .then(() => {
        setUndo(e);
        load();
      })
      .catch((x) => setErr((x as Error).message));
  return (
    <div className="app">
      <header className="topbar">
        <strong className="brand">LACUNA</strong>
        <span className="grow" />
        {nav}
      </header>
      <main className="home">
        <div className="home-hero">
          <h1>{t("剧集")}</h1>
          <p className="muted">{t("导入 Leon 和 Pei 的两条分轨，AI 先剪第一刀，你来过目、试听、导出。")}</p>
        </div>
        <ImportPanel episodes={list} onEpisodesChanged={reload} onOpen={open} />
        {err && <p className="error">{err}</p>}
        {list?.length === 0 && <p className="muted">{t("工作区里还没有剧集。点「导入新一集」，选 Leon 和 Pei 的两条分轨。")}</p>}
        {!list && !err && <EpisodeListSkeleton />}
        <ul className="ep-list">
          {list?.map((e) => (
            <EpisodeCard
              key={e.id}
              e={e}
              href={`#/ep/${encodeURIComponent(e.id)}/listen`}
              actions={
                <button
                  type="button"
                  className="btn btn-ghost btn-small ep-archive"
                  onClick={() => void archive(e)}
                  aria-label={t("归档「{title}」", { title: e.title })}
                  title={t("归档：从列表里收起来，随时能在「已归档」里恢复")}
                >
                  {t("归档")}
                </button>
              }
            />
          ))}
        </ul>
        {archived > 0 && (
          <p className="ep-archived-link">
            <a className="btn btn-outline btn-small linkbtn" href="#/archive" data-testid="archived-link">
              {t("已归档 · {n}", { n: archived })}
            </a>
          </p>
        )}
      </main>
      {undo && (
        <div className="toast ep-toast" role="status">
          <span>{t("已归档「{title}」", { title: undo.title })}</span>
          <button
            type="button"
            className="btn btn-small ep-toast-undo"
            onClick={() =>
              void episodesApi.restore(undo.id).then(() => {
                setUndo(null);
                load();
              })
            }
          >
            {t("撤销")}
          </button>
        </div>
      )}
    </div>
  );
}
