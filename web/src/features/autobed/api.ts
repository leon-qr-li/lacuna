// 自动铺底 (docs/decisions/2026-10-30-auto-bed.md): ticked songs fill the talk no other music covers (lacuna_app/routes/autobed.py)
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
}

export const autobedApi = {
  view: (id: string) => req<AutoBedView>("GET", `${ep(id)}/music/autobed`),
  fill: (id: string, asset_ids: string[], seed?: number) =>
    req<MusicView>("POST", `${ep(id)}/music/autobed`, { asset_ids, seed: seed ?? Math.floor(Math.random() * 1e9) }),
};
