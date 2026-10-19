// 手动剪辑 (decision manual-editing): waveform tiles, transcript words, cut a selection (lacuna_app/manual.py)
import type { Episode } from "../../api";
import { ep, req } from "../../api";

export const TILE_S = 10; // seconds per waveform tile (manual.TILE_S)
export const WORDS_S = 30; // seconds per transcript request

export interface WaveTile {
  tile: number;
  start: number;
  per_s: number;
  tracks: { name: string; peaks: number[] }[]; // 0-100
}

/** [text, start, end] in timeline seconds */
export type Word = [string, number, number];
export interface Utterance {
  speaker: string;
  words: Word[];
}

export const manualApi = {
  wave: (id: string, version: string, tile: number) =>
    req<WaveTile>("GET", `${ep(id)}/manual/wave?tile=${tile}&v=${encodeURIComponent(version)}`),
  words: (id: string, version: string, t0: number, t1: number) =>
    req<{ utterances: Utterance[] }>("GET", `${ep(id)}/manual/words?t0=${t0}&t1=${t1}&v=${encodeURIComponent(version)}`),
  /** track = null: remove from every track (the timeline closes up); a name: silence only that host */
  cut: (id: string, start: number, end: number, track: string | null, playhead: number) =>
    req<Episode & { edit_id: string }>("POST", `${ep(id)}/manual/cut`, { start, end, track, playhead }),
};
