import { useCallback, useEffect, useState } from "react";
import { failure, req } from "../../api";

/** An opener / ending default: the asset and its file name (null name: the file left the library). */
export interface DefaultTrack {
  asset_id: string;
  name: string | null;
}

export interface Album {
  id: string;
  name: string;
  about: string;
  created: string;
  cover_url: string | null;
  episodes: string[];
  intro: DefaultTrack | null;
  outro: DefaultTrack | null;
}

export interface AlbumsView {
  albums: Album[];
  /** episode id -> album id (episodes in no album are left out) */
  episodes: Record<string, string>;
  /** the project's own opener / ending; an album's overrides it */
  project: { intro: DefaultTrack | null; outro: DefaultTrack | null };
}

export interface AlbumFields {
  name?: string;
  about?: string;
  /** asset id; "" = use the project's */
  intro?: string;
  outro?: string;
}

const album = (id: string) => `/api/albums/${encodeURIComponent(id)}`;

export const albumsApi = {
  list: () => req<AlbumsView>("GET", "/api/albums"),
  create: (body: AlbumFields & { name: string; episodes?: string[] }) =>
    req<AlbumsView & { created: string }>("POST", "/api/albums", body),
  update: (id: string, body: AlbumFields) => req<AlbumsView>("PATCH", album(id), body),
  remove: (id: string) => req<AlbumsView & { moved: string[] }>("DELETE", album(id)),
  projectMusic: (body: { intro?: string; outro?: string }) => req<AlbumsView>("PATCH", "/api/albums/project", body),
  setEpisode: (episode: string, albumId: string | null) =>
    req<AlbumsView>("POST", `/api/episodes/${encodeURIComponent(episode)}/album`, { album: albumId }),
  cover: async (id: string, file: File): Promise<AlbumsView> => {
    const url = `${album(id)}/cover`;
    const r = await fetch(url, { method: "POST", body: file, headers: { "Content-Type": file.type } });
    if (!r.ok) throw await failure(r, url);
    return (await r.json()) as AlbumsView;
  },
};

/** The project's albums, reloaded on demand; `set` takes the view a change answered with. */
export function useAlbums() {
  const [view, setView] = useState<AlbumsView | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const reload = useCallback(() => {
    albumsApi
      .list()
      .then(setView)
      .catch((e) => setErr(String((e as Error).message ?? e)));
  }, []);
  useEffect(reload, [reload]);
  return { view, err, reload, set: setView };
}

/** Where an episode's album page lives. */
export const albumHref = (id: string) => `#/album/${encodeURIComponent(id)}`;
