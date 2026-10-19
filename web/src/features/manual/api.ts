// 手动剪辑 (decision manual-editing): waveform tiles, transcript words, cut a selection (lacuna_app/manual.py)
import type { Episode } from "../../api";
import { ep, req } from "../../api";

export const TILE_S = 10; // seconds per waveform tile (manual.TILE_S)
export const TEXT_S = 30; // seconds per transcript request

export interface WaveTile {
  tile: number;
  start: number;
  per_s: number;
  tracks: { name: string; peaks: number[] }[]; // 0-100
}

/** [text, start, end (timeline s), id of the edit that removed it or null, start in the recording] */
export type Word = [string, number, number, string | null, number];
/** one host's run of words */
export interface Line {
  speaker: string;
  start: number;
  words: Word[];
}

export const manualApi = {
  wave: (id: string, version: string, tile: number) =>
    req<WaveTile>("GET", `${ep(id)}/manual/wave?tile=${tile}&v=${encodeURIComponent(version)}`),
  transcript: (id: string, version: string, t0: number, t1: number) =>
    req<{ lines: Line[] }>("GET", `${ep(id)}/manual/transcript?t0=${t0}&t1=${t1}&v=${encodeURIComponent(version)}`),
  /** track = null: remove from every track (the timeline closes up); a name: silence only that host */
  cut: (id: string, start: number, end: number, track: string | null, playhead: number) =>
    req<Episode & { edit_id: string }>("POST", `${ep(id)}/manual/cut`, { start, end, track, playhead }),
};
