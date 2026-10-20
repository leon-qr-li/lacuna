// English um / uh (decision english-fillers): every filler of the episode, cut the ones still heard (lacuna_app/fillers.py)
import type { Episode } from "../../api";
import { ep, req } from "../../api";

export interface Filler {
  track: string;
  text: string;
  t: number; // timeline seconds
  len: number;
  gone: string | null; // id of the edit that removed it
}
export interface Fillers {
  language: string;
  items: Filler[];
  hosts: { name: string; left: number; cut: number }[];
  left: number;
  cut: number;
}

export const fillersApi = {
  list: (id: string) => req<Fillers>("GET", `${ep(id)}/fillers`),
  /** tracks = null: every host */
  cut: (id: string, tracks: string[] | null, playhead: number) =>
    req<Episode & { cut: number }>("POST", `${ep(id)}/fillers/cut`, { tracks, playhead }),
};
