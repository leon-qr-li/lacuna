// The proper-noun check made at import (lacuna_app/name_check.py, routes/name_check.py)
import type { Episode } from "../../api";
import { ep, req } from "../../api";

export interface NamePlace {
  speaker: string;
  start: number;
  end: number;
}
export interface NameFix {
  wrong: string;
  right: string;
  why: string;
  count: number;
  places: NamePlace[];
  /** applied: changed at import; kept: put back as heard */
  state: "applied" | "kept";
}

export const nameCheckApi = {
  list: (id: string) => req<{ rows: NameFix[]; on: boolean }>("GET", `${ep(id)}/names`),
  keep: (id: string, f: NameFix, playhead: number) =>
    req<Episode & { names: NameFix[]; changed: number }>("POST", `${ep(id)}/names/keep`, { wrong: f.wrong, right: f.right, playhead }),
};
