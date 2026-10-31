// 逐字稿搜索 in 整集试听 (lacuna_app/transcript_search.py, routes/transcript_search.py)
import { useSyncExternalStore } from "react";
import { ep, req } from "../../api";

/** one place the text is said: timeline seconds; `gone` = every word of it is cut (struck through) */
export interface Hit {
  start: number;
  end: number;
  speaker: string;
  gone: boolean;
}

export const searchApi = {
  find: (id: string, version: string, q: string) =>
    req<{ hits: Hit[]; more: boolean }>("GET", `${ep(id)}/transcript/search?q=${encodeURIComponent(q)}&v=${encodeURIComponent(version)}`, undefined, {
      timeout: 20_000,
    }),
};

/** What the search box found, shared with the transcript (marks the words) and the timeline ruler (ticks). */
export interface Found {
  q: string;
  hits: Hit[];
  cur: number; // the place jumped to, -1 before the first jump
}
const EMPTY: Found = { q: "", hits: [], cur: -1 };
let found = EMPTY;
const subs = new Set<() => void>();
export const setFound = (f: Found) => {
  found = f;
  subs.forEach((s) => s());
};
export const clearFound = () => setFound(EMPTY);
const subscribe = (s: () => void) => {
  subs.add(s);
  return () => void subs.delete(s);
};
export const useFound = () => useSyncExternalStore(subscribe, () => found);

/** Index of the hit that word [a, b] of `speaker` is part of, or -1 (a cut word sits at its cut point, a = b). */
export const hitOf = (hits: Hit[], speaker: string, a: number, b: number) =>
  hits.findIndex((h) => h.speaker === speaker && a >= h.start - 0.002 && b <= h.end + 0.002);
