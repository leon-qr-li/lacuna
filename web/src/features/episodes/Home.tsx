import { useCallback, useEffect, useState, type ReactNode } from "react";
import type { EpisodeListItem } from "../../api";
import { api } from "../../api";
import { t } from "../../i18n";
import { hostList, useShow } from "../show/api";
import { ShowSetup } from "../show/ShowView";
import { EpisodeListSkeleton } from "../loading/Loading";
import { ImportPanel } from "../import/ImportPanel";
import { AlbumDialog } from "../albums/AlbumDialog";
import { AlbumStrip } from "../albums/AlbumPage";
import { AlbumRow } from "../albums/AlbumRow";
import { MoveToAlbum } from "../albums/MoveToAlbum";
import { ProjectCrumb } from "../projects/ProjectMenu";
import { loadProjects, useProjects } from "../projects/api";
import { ProjectAvatar } from "../projects/Avatar";
import { albumHref, useAlbums, type Album } from "../albums/api";
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
  const show = useShow();
  const names = hostList(show);
  const proj = useProjects()?.current;
  const albums = useAlbums();
  // 新建专辑 (preset: the episode whose card asked) or 专辑设置 of the one album shown inline
  const [dialog, setDialog] = useState<{ album?: Album; preset?: string } | null>(null);
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
  // signing in with two or more projects: pick one on 所有项目 first (once per visit)
  useEffect(() => {
    if (window.location.hash) return;
    let seen = false;
    try {
      seen = sessionStorage.getItem("lacuna.projects-seen") === "1";
      sessionStorage.setItem("lacuna.projects-seen", "1");
    } catch {
      /* private mode */
    }
    if (seen) return;
    void loadProjects().then((sp) => {
      if ((sp?.mine.length ?? 0) > 1 && !window.location.hash) window.location.hash = "#/projects";
    });
  }, []);
  useEffect(() => {
    if (!undo) return;
    const timer = window.setTimeout(() => setUndo(null), 8000);
    return () => window.clearTimeout(timer);
  }, [undo]);
  const reloadAlbums = albums.reload;
  const reload = useCallback(() => {
    load();
    reloadAlbums();
  }, [load, reloadAlbums]);
  const open = useCallback((id: string) => go(id, "review"), []);
  const archive = (e: EpisodeListItem) =>
    episodesApi
      .archive(e.id)
      .then(() => {
        setUndo(e);
        load();
      })
      .catch((x) => setErr((x as Error).message));
  // the one album that holds every episode: new imports go there too unless Leon picks otherwise
  const v0 = albums.view;
  const onlyAlbum = v0?.albums.length === 1 && list?.length && list.every((e) => v0.episodes[e.id]) ? v0.albums[0].id : "";
  const cards = (eps: EpisodeListItem[]) => (
    <ul className="ep-list">
      {eps.map((e) => (
        <EpisodeCard
          key={e.id}
          e={e}
          href={`#/ep/${encodeURIComponent(e.id)}/listen`}
          actions={
            <>
              {albums.view && !!albums.view.albums.length && (
                <MoveToAlbum
                  episode={e.id}
                  title={e.title}
                  view={albums.view}
                  onMoved={albums.set}
                  onNew={() => setDialog({ preset: e.id })}
                />
              )}
              <button
                type="button"
                className="btn btn-ghost btn-small ep-archive"
                onClick={() => void archive(e)}
                aria-label={t("归档「{title}」", { title: e.title })}
                title={t("归档：从列表里收起来，随时能在「已归档」里恢复")}
              >
                {t("归档")}
              </button>
            </>
          }
        />
      ))}
    </ul>
  );
  return (
    <div className="app">
      <header className="topbar">
        <strong className="brand">LACUNA</strong>
        <ProjectCrumb />
        <span className="grow" />
        {nav}
      </header>
      <main className="home">
        <div className="home-hero">
          <h1 className="home-title">
            {proj && <ProjectAvatar p={proj} size={40} />}
            {proj?.name ?? show?.show_name ?? t("剧集")}
          </h1>
          <p className="muted">
            {names
              ? t("导入 {names} 的分轨，AI 先剪第一刀，你来过目、试听、导出。", { names })
              : t("导入每位主持人的分轨，AI 先剪第一刀，你来过目、试听、导出。")}
          </p>
        </div>
        <ShowSetup />
        {!show?.needs_setup && (
          <ImportPanel
            episodes={list}
            onEpisodesChanged={reload}
            onOpen={open}
            albums={albums.view?.albums}
            album={onlyAlbum}
          />
        )}
        {err && <p className="error">{err}</p>}
        {list?.length === 0 && !show?.needs_setup && (
          <p className="muted">{t("这个节目里还没有剧集。点「导入新一集」，选每位主持人的分轨。")}</p>
        )}
        {!list && !err && <EpisodeListSkeleton />}
        {(() => {
          const v = albums.view;
          const all = list ?? [];
          if (!v || !v.albums.length)
            return (
              <>
                {v && !!all.length && (
                  <button type="button" className="btn btn-outline btn-small home-new-album" onClick={() => setDialog({})} data-testid="album-new">
                    {t("＋ 新专辑")}
                  </button>
                )}
                {!!all.length && <div className="home-sec"><h2 className="sub">{t("剧集")}</h2><span className="muted small">{t("{n} 集", { n: all.length })}</span></div>}
                {cards(all)}
              </>
            );
          const loose = all.filter((e) => !v.episodes[e.id]);
          // one album holding every episode: no extra click, its episodes right here under its strip
          if (v.albums.length === 1 && !loose.length && all.length) {
            const only = v.albums[0];
            return (
              <>
                <div className="home-sec">
                  <h2 className="sub">{t("专辑")}</h2>
                </div>
                <AlbumStrip album={only} view={v} onEdit={() => setDialog({ album: only })} />
                <p className="row gap8 home-new-album">
                  <a className="btn btn-ghost btn-small" href={albumHref(only.id)}>
                    {t("打开专辑页")}
                  </a>
                  <button type="button" className="btn btn-outline btn-small" onClick={() => setDialog({})} data-testid="album-new">
                    {t("＋ 新专辑")}
                  </button>
                </p>
                <div className="home-sec">
                  <h2 className="sub">{t("剧集")}</h2>
                  <span className="muted small">{t("{n} 集", { n: all.length })}</span>
                </div>
                {cards(all)}
              </>
            );
          }
          return (
            <>
              <div className="home-sec">
                <h2 className="sub">{t("专辑")}</h2>
              </div>
              <AlbumRow view={v} onNew={() => setDialog({})} />
              {!!loose.length && (
                <>
                  <div className="home-sec">
                    <h2 className="sub">{t("不在专辑里")}</h2>
                    <span className="muted small">{t("{n} 集", { n: loose.length })}</span>
                  </div>
                  {cards(loose)}
                </>
              )}
            </>
          );
        })()}
        {archived > 0 && (
          <p className="ep-archived-link">
            <a className="btn btn-outline btn-small linkbtn" href="#/archive" data-testid="archived-link">
              {t("已归档 · {n}", { n: archived })}
            </a>
          </p>
        )}
      </main>
      {dialog && albums.view && (
        <AlbumDialog
          album={dialog.album}
          view={albums.view}
          loose={list?.filter((e) => !albums.view!.episodes[e.id] && e.id !== dialog.preset)}
          preset={dialog.preset ? [dialog.preset] : undefined}
          onClose={() => setDialog(null)}
          onSaved={(v, r) => {
            setDialog(null);
            albums.set(v);
            if (r.created) window.location.hash = albumHref(r.created);
          }}
        />
      )}
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
