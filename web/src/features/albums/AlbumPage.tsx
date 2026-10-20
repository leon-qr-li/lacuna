import { useCallback, useEffect, useRef, useState } from "react";
import type { EpisodeListItem } from "../../api";
import { t } from "../../i18n";
import { EpisodeCard } from "../episodes/EpisodeCard";
import { episodesApi } from "../episodes/api";
import { ImportPanel } from "../import/ImportPanel";
import { libraryApi, type Asset, type LibraryView } from "../library/api";
import { BusyLabel, EpisodeListSkeleton } from "../loading/Loading";
import { AlbumDialog } from "./AlbumDialog";
import { AlbumCover } from "./Cover";
import { MoveToAlbum } from "./MoveToAlbum";
import { useAlbums, type Album, type AlbumsView, type DefaultTrack } from "./api";

const albumId = () => decodeURIComponent(/^#\/album\/([^/?]+)/.exec(window.location.hash)?.[1] ?? "");

function useHashAlbum() {
  const [id, setId] = useState(albumId);
  useEffect(() => {
    const on = () => setId(albumId());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return id;
}

/** #/album/<id>: the album's strip (cover, defaults, 专辑设置), import into it, its episodes and its own media. */
export function AlbumPage() {
  const id = useHashAlbum();
  const albums = useAlbums();
  const [list, setList] = useState<EpisodeListItem[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [dialog, setDialog] = useState<{ edit: boolean; preset?: string } | null>(null);
  const loadEpisodes = useCallback(() => {
    episodesApi
      .episodes()
      .then((r) => setList(r.episodes))
      .catch((e) => setErr(String((e as Error).message ?? e)));
  }, []);
  useEffect(loadEpisodes, [loadEpisodes]);
  const reload = useCallback(() => {
    loadEpisodes();
    albums.reload();
  }, [loadEpisodes, albums]);
  const open = useCallback((ep: string) => {
    window.location.hash = `#/ep/${encodeURIComponent(ep)}/review`;
  }, []);

  const view = albums.view;
  const album = view?.albums.find((a) => a.id === id);
  if (albums.err || err) return <main className="home"><p className="error">{albums.err ?? err}</p></main>;
  if (!view || !list) return <main className="home"><EpisodeListSkeleton /></main>;
  if (!album)
    return (
      <main className="home">
        <p className="muted">{t("没有这个专辑，可能已经删了。")}</p>
        <a className="btn btn-outline btn-small" href="#/">
          {t("回到剧集")}
        </a>
      </main>
    );
  const eps = list.filter((e) => view.episodes[e.id] === album.id);
  return (
    <main className="home alb-page" data-testid="album-page">
      <AlbumStrip album={album} view={view} onEdit={() => setDialog({ edit: true })} />
      <ImportPanel episodes={list} onEpisodesChanged={reload} onOpen={open} albums={view.albums} album={album.id} />
      <h2 className="sub">{t("这个专辑的剧集")}</h2>
      {!eps.length && <p className="muted">{t("专辑里还没有剧集。导入新一集，或者在剧集卡片上点「移到专辑」。")}</p>}
      <ul className="ep-list">
        {eps.map((e) => (
          <EpisodeCard
            key={e.id}
            e={e}
            href={`#/ep/${encodeURIComponent(e.id)}/listen`}
            actions={<MoveToAlbum episode={e.id} title={e.title} view={view} onMoved={albums.set} onNew={() => setDialog({ edit: false, preset: e.id })} />}
          />
        ))}
      </ul>
      <AlbumShelf album={album} />
      {dialog && (
        <AlbumDialog
          album={dialog.edit ? album : undefined}
          view={view}
          preset={dialog.preset ? [dialog.preset] : undefined}
          onClose={() => setDialog(null)}
          onSaved={(v, r) => {
            setDialog(null);
            albums.set(v);
            if (r.deleted) window.location.hash = "#/";
          }}
        />
      )}
    </main>
  );
}

/** The album's header: cover, name, episode count, and where its opener / ending come from. */
export function AlbumStrip({ album, view, onEdit }: { album: Album; view: AlbumsView; onEdit: () => void }) {
  const slot = (label: string, own: DefaultTrack | null, project: DefaultTrack | null) => {
    const name = (own ?? project)?.name;
    return (
      <div className="alb-slot">
        <span className="alb-label">{label}</span>
        <span className="alb-slot-name">{name ?? t("没有设")}</span>
        {own || project ? <span className={`alb-from${own ? " alb-from-own" : ""}`}>{own ? t("本专辑") : t("沿用项目")}</span> : <span />}
      </div>
    );
  };
  return (
    <section className="alb-strip" aria-label={t("专辑")} data-testid="album-strip">
      <AlbumCover a={album} size={88} />
      <div className="alb-strip-main">
        <h1>{album.name}</h1>
        <p className="muted small">
          {t("{n} 集", { n: album.episodes.length })}
          {album.about && ` · ${album.about}`}
        </p>
      </div>
      <div className="alb-slots">
        {slot(t("默认片头"), album.intro, view.project.intro)}
        {slot(t("默认片尾"), album.outro, view.project.outro)}
      </div>
      <button type="button" className="btn btn-outline alb-edit" onClick={onEdit} data-testid="album-settings">
        {t("专辑设置")}
      </button>
    </section>
  );
}

/** 这个专辑的素材: what only this album's episodes use, and an upload that files new media under it. */
function AlbumShelf({ album }: { album: Album }) {
  const [lib, setLib] = useState<LibraryView | null>(null);
  const [kind, setKind] = useState("other");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const load = useCallback(() => {
    libraryApi
      .library()
      .then(setLib)
      .catch(() => setLib(null));
  }, []);
  useEffect(load, [load]);
  const mine: Asset[] = lib?.assets.filter((a) => a.albums?.includes(album.id)) ?? [];
  const add = async (files: File[]) => {
    setBusy(true);
    const done: string[] = [];
    for (const f of files) {
      try {
        const r = await libraryApi.uploadAsset(f, kind, "", "", album.id);
        done.push(
          r.duplicate && r.asset.shared
            ? t("素材库里已经有这首（整个项目都能用）：{name}", { name: r.asset.name })
            : t("已加到这个专辑：{name}", { name: r.asset.name }),
        );
      } catch (e) {
        done.push(t("没加进去：{name}", { name: f.name }) + `（${(e as Error).message}）`);
      }
    }
    setBusy(false);
    setMsg(done.join("；"));
    load();
  };
  return (
    <section className="alb-shelf" aria-label={t("这个专辑的素材")} data-testid="album-shelf">
      <div className="row gap8 wrap alb-shelf-head">
        <h2 className="sub">{t("这个专辑的素材")}</h2>
        <span className="grow" />
        <a className="btn btn-ghost btn-small" href="#/library">
          {t("去素材库管理")}
        </a>
      </div>
      {mine.length ? (
        <ul className="alb-shelf-list">
          {mine.map((a) => (
            <li key={a.id}>
              <span className="alb-shelf-kind small">{a.kind_label}</span>
              <span className="alb-shelf-name">{a.name}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted small">{t("还没有只给这个专辑用的素材；整个项目的素材这里的剧集都能用。")}</p>
      )}
      <div className="row gap8 wrap">
        <button type="button" className="btn btn-outline" disabled={busy || !lib} onClick={() => input.current?.click()} data-testid="album-upload">
          <BusyLabel busy={busy} label={t("给这个专辑添加素材")} busyLabel={t("正在加入…")} />
        </button>
        <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label={t("上传的文件当作")}>
          {Object.entries(lib?.kinds ?? {}).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        <input
          ref={input}
          type="file"
          multiple
          accept=".mp3,.wav,.flac,.m4a,.aac,.ogg,.opus,.aif,.aiff,.wma,audio/*"
          hidden
          aria-label={t("选择音乐文件")}
          onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            e.target.value = "";
            if (files.length) void add(files);
          }}
        />
      </div>
      {msg && (
        <p className="small muted" role="status">
          {msg}
        </p>
      )}
    </section>
  );
}
