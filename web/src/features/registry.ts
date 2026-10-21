import type { ReactNode } from "react";
import type { Episode } from "../api";

/**
 * Feature registry. Each folder `src/features/<name>/` has an `index.tsx` that exports
 * `feature: Feature`; they are picked up automatically, so a new page, episode tab or top-bar
 * link means a new folder, not an edit to App.tsx (fewer merge conflicts between threads).
 * Keep a feature's API calls and types in its own `api.ts` and its styles in its own `.css`.
 */

export interface EpisodeTabProps {
  id: string;
  ep: Episode;
  /** A toast; `undo` adds a small 撤销 button (bulk actions). */
  flash: (msg: string, opts?: { undo?: boolean }) => void;
  pauseMain: () => void;
  /** Replace the episode shown everywhere (a tab that changed it, e.g. a volume edit on 声音). */
  onEpisode?: (ep: Episode) => void;
}

/** A tab on the episode screen, shown at `#/ep/<id>/<mode>` (after 整集试听 and 改动审阅). */
export interface EpisodeTab {
  mode: string;
  label: string;
  order: number;
  /** Tabs sharing a group show as one step in the episode flow, with sub-tabs (e.g. "publish"). */
  group?: string;
  render: (p: EpisodeTabProps) => ReactNode;
}

/** A top-level page at `#/<path>`. */
export interface Page {
  path: string;
  title: string;
  render: () => ReactNode;
}

/** A link in the top bar; `on` says on which screens. On its own page the link stays, selected. */
export interface NavLink {
  order: number;
  path: string;
  render: () => ReactNode;
  on: ("home" | "episode" | "page")[];
}

export interface Feature {
  tabs?: EpisodeTab[];
  pages?: Page[];
  nav?: NavLink[];
}

const mods = import.meta.glob<{ feature: Feature }>("./*/index.tsx", { eager: true });
const features = Object.keys(mods)
  .sort()
  .map((k) => mods[k].feature);

const byOrder = <T extends { order: number }>(xs: T[]) => [...xs].sort((a, b) => a.order - b.order);

export const tabs: EpisodeTab[] = byOrder(features.flatMap((f) => f.tabs ?? []));
export const pages: Page[] = features.flatMap((f) => f.pages ?? []);
export const navLinks: NavLink[] = byOrder(features.flatMap((f) => f.nav ?? []));

/** `aria-current` for a top-bar link to `#/<path>`: "page" while that page is open (styled in episodes.css). */
export const navCurrent = (path: string) =>
  window.location.hash === `#/${path}` || window.location.hash.startsWith(`#/${path}/`) ? ("page" as const) : undefined;
