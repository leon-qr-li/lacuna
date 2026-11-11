// 自动铺底 (docs/decisions/2026-10-30-auto-bed.md): each ticked song once, at random in the talk no other music covers (lacuna_app/routes/autobed.py)
import { ep, req } from "../../api";
import type { Kind, MusicView } from "../library/api";

export interface BedSong {
  id: string;
  name: string;
  kind: Kind;
  kind_label: string;
  duration_s: number;
  used_as: string | null; // already the episode's 片头 / 间奏 / …
  in_bed: boolean; // in the current 自动铺底
}

export interface AutoBedView {
  songs: BedSong[];
  free_s: number; // the free stretches together
  stretches: number;
  beds: number; // 铺底 on the episode now (自动铺底 or by hand)
}

export type AutoBedResult = MusicView & { placed?: number; removed?: number };

export const autobedApi = {
  view: (id: string) => req<AutoBedView>("GET", `${ep(id)}/music/autobed`),
  /** each ticked song once, at random in the free talk, straight onto the episode */
  fill: (id: string, asset_ids: string[], seed?: number) =>
    req<AutoBedResult>("POST", `${ep(id)}/music/autobed`, { asset_ids, seed: seed ?? Math.floor(Math.random() * 1e9) }),
  /** 「取消所有铺底」 */
  clear: (id: string) => req<AutoBedResult>("DELETE", `${ep(id)}/music/autobed`),
};
