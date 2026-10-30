// 间隙 (docs/decisions/2026-10-30-edit-gaps.md): silence opened between two sentences while editing (lacuna_app/routes/gaps.py)
import { ep, req } from "../../api";
import type { MusicView } from "../library/api";

export const DEFAULT_LEN = 15; // seconds (Leon 2026-10-30)
export const LENGTHS = [5, 10, 15, 30];

export interface Gap {
  id: string;
  voice_s: number; // on the voice cut (the editing timeline)
  final_s: number; // on the final mix
  len_s: number;
  filled_by: string | null; // the interlude playing in it
  music_name: string | null;
}

export interface GapsView {
  gaps: Gap[];
  inserts: [number, number][];
  gap_id?: string;
  removed_music?: number;
}

export const gapsApi = {
  list: (id: string) => req<GapsView>("GET", `${ep(id)}/gaps`),
  add: (id: string, voice_s: number, len_s: number = DEFAULT_LEN) => req<GapsView>("POST", `${ep(id)}/gaps`, { voice_s, len_s }),
  setLen: (id: string, gid: string, len_s: number) => req<GapsView>("PATCH", `${ep(id)}/gaps/${gid}`, { len_s }),
  remove: (id: string, gid: string) => req<GapsView>("DELETE", `${ep(id)}/gaps/${gid}`),
  /** 「给间隙自动配乐」: a suggestion on the 配乐 page */
  fill: (id: string) => req<MusicView>("POST", `${ep(id)}/music/gaps/auto`),
  /** 「放到 → 间隙」: a song, or a placed piece (pid), into the first gap without music, left to right */
  place: (id: string, what: { asset_id: string } | { pid: string }) => req<MusicView>("POST", `${ep(id)}/music/gaps/place`, what),
};
