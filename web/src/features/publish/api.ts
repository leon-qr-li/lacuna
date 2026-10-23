// API of this feature (moved out of src/api.ts so features don't all edit one file)
import type { Usage } from "../../api";
import { ep, req } from "../../api";

export interface PublishChapter {
  t: number;
  time: string;
  heading: string;
}

export interface PublishName {
  heard: string;
  suggested: string;
  why: string;
  state: "open" | "applied" | "ignored";
}

export interface PublishPack {
  title: string;
  alt_titles: string[];
  blurb: string;
  markdown: string;
  edited: boolean;
  chapters: PublishChapter[];
  names: PublishName[];
  stale: boolean;
  gone: string[];
  notes: string[];
  adapter: string;
  usage: Partial<Usage>;
  /** goes up at every save (co-editing: a save from an older version is refused) */
  rev?: number;
  generated_at: string;
  library: boolean;
  /** how detailed the show-notes timeline is (Leon 2026-10-23); packs from before levels are "full" */
  level: PublishLevel;
  /** timeline entries each level shows */
  counts: Partial<Record<PublishLevel, number>>;
  /** final-cut length in seconds */
  duration: number;
}

export type PublishLevel = "lean" | "std" | "full";

export interface PublishJob {
  state: "running" | "done" | "error";
  stage: string;
  started: number;
  finished: number | null;
  error: string | null;
}

export interface PublishView {
  pack: PublishPack | null;
  job: PublishJob | null;
  notes_path: string;
  editor: string;
  editor_note: string;
}


export const publishApi = {
  publish: (id: string) => req<PublishView>("GET", `${ep(id)}/publish`),
  generatePublish: (id: string) => req<PublishView>("POST", `${ep(id)}/publish/generate`),
  retimePublish: (id: string) => req<PublishView>("POST", `${ep(id)}/publish/retime`),
  // `rev`: the pack version on screen; someone saved since -> 409 with `stale` (features/coedit)
  editPublish: (id: string, body: { markdown?: string | null; title?: string; rev?: number }) =>
    req<PublishView>("PUT", `${ep(id)}/publish`, body),
  // local re-filter of the timeline, no AI call; replaces hand-edited show notes (the page asks first)
  setPublishLevel: (id: string, level: PublishLevel, rev?: number) =>
    req<PublishView>("PUT", `${ep(id)}/publish/level`, { level, rev }),
  publishName: (id: string, heard: string, action: "apply" | "ignore") =>
    req<PublishView>("POST", `${ep(id)}/publish/names`, { heard, action }),
};
