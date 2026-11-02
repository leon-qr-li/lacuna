import { req } from "../../api";
import { formatTitle, type Naming } from "../album-naming/api";

/** The episode's name (lacuna_app/episode_name.py): `name` is the part the user named ("" = not named yet);
 *  in an album with a naming format `title` is that name inside the format. */
export type EpisodeName = {
  id: string;
  title: string;
  name: string;
  named: boolean;
  album: { id: string; name: string } | null;
  naming: Naming | null;
};

const base = (id: string) => `/api/episodes/${encodeURIComponent(id)}/name`;

export const nameApi = {
  get: (id: string) => req<EpisodeName>("GET", base(id)),
  /** "" = back to only the number. Also becomes the publish pack's title. */
  set: async (id: string, name: string) => {
    const v = await req<EpisodeName>("PUT", base(id), { name });
    window.dispatchEvent(new CustomEvent<EpisodeName>(RENAMED, { detail: v }));
    return v;
  },
};

/** Sent on `window` after every rename, so the top bar shows the new name whichever page renamed it. */
export const RENAMED = "lacuna-episode-renamed";

/** What the episode will be called with `name` (the album's format around it). */
export const titleFor = (v: Pick<EpisodeName, "id" | "naming">, name: string) => formatTitle(v.naming, v.id, name);

/** An episode nobody has named yet: its title is only its number (home card, 还没起名). */
export const unnamed = (e: { id: string; title: string }) => e.title.trim() === e.id;

/** Call `fn` after each rename; returns the unsubscribe (a useEffect cleanup). */
export function onRenamed(fn: (v: EpisodeName) => void): () => void {
  const h = (e: Event) => fn((e as CustomEvent<EpisodeName>).detail);
  window.addEventListener(RENAMED, h);
  return () => window.removeEventListener(RENAMED, h);
}
