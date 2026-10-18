import type { EpisodeListItem } from "../../api";
import { req } from "../../api";

export type ArchivedItem = EpisodeListItem & { archived_at: string };

const ep = (id: string) => `/api/episodes/${encodeURIComponent(id)}`;

export const episodesApi = {
  episodes: () => req<{ episodes: EpisodeListItem[]; archived: number; editor: string }>("GET", "/api/episodes"),
  archived: () => req<{ episodes: ArchivedItem[] }>("GET", "/api/archive"),
  archive: (id: string) => req<{ archived: string; at: string }>("POST", `${ep(id)}/archive`),
  restore: (id: string) => req<{ restored: string }>("POST", `${ep(id)}/restore`),
  remove: (id: string) => req<{ deleted: string; freed_bytes: number; tracks: string[]; assets?: string[] }>("DELETE", ep(id)),
};
