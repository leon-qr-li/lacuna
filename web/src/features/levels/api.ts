// 声音 (backlog 7): measured loudness and per-track gain of the episode's hosts (lacuna_app/levels.py)
import type { AB, Episode } from "../../api";
import { ep, req } from "../../api";

export interface TrackLevel {
  name: string;
  gain_db: number;
  lufs: number | null; // raw recording, measured once
  level_lufs: number | null; // as heard now (raw + gain)
  suggested_gain_db: number | null;
  peak_db: number | null;
  loud_peak_db: number | null;
  out_peak_db: number | null;
  clip_count: number; // clipping spots in the recording (repaired automatically where safe)
  clip_repaired: number;
  clip_kept: number; // spots left as recorded that are still in the cut
  clip_times: number[]; // those spots, seconds on the current cut (first 30)
}

export interface Levels {
  target_lufs: number;
  tracks: TrackLevel[];
  even: boolean;
  min_db: number;
  max_db: number;
}

type WithLevels = Episode & { levels: Levels; changed: Record<string, number> };

export const levelsApi = {
  levels: (id: string) => req<Levels>("GET", `${ep(id)}/levels`),
  setGain: (id: string, track: string, gain_db: number, playhead?: number) =>
    req<WithLevels>("POST", `${ep(id)}/levels/${encodeURIComponent(track)}`, { gain_db, playhead }),
  /** 原始 / 调整后 around a moment of the current cut */
  ab: (id: string, at: number) => req<AB>("GET", `${ep(id)}/levels/ab?at=${Math.max(0, at).toFixed(2)}`),
  auto: (id: string, playhead?: number) => req<WithLevels>("POST", `${ep(id)}/levels/auto`, { playhead }),
};
