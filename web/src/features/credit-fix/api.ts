// 一键修复曲名和作者 (decision 2026-10-30-credit-fix)
import { req } from "../../api";
import type { Credit, CreditStatus } from "../library/api";

export type Found = Pick<Credit, "title" | "artist" | "composer" | "album" | "film" | "year">;

export interface FixFile {
  id: string;
  name: string;
  duration_s: number;
  kind_label: string;
  credit_line: string;
  status: CreditStatus;
}

export interface FixResult {
  asset_id: string;
  name: string;
  duration_s: number;
  old_line: string;
  old_status: CreditStatus;
  found: Found;
  /** the credit line the found fields make ("" when nothing was found) */
  line: string;
  confidence: number;
  note: string;
  alternatives: string[];
  /** starts ticked (found, and LACUNA is fairly sure) */
  pick: boolean;
}

export interface FixJob {
  state: "running" | "done" | "failed";
  prompt: string;
  redo: boolean;
  started_at: string;
  files: FixFile[];
  results: FixResult[];
  sources: string[];
  message: string;
}

export interface FixView {
  available: boolean;
  /** the music this button covers: an episode's own, or the library's shared music */
  own: number;
  /** of those, not confirmed yet */
  unknown: number;
  files: FixFile[];
  job: FixJob | null;
  applied?: number;
}

const URL = "/api/library/credit-fix";
const q = (episode?: string) => (episode ? `?${new URLSearchParams({ episode })}` : "");

export const creditFixApi = {
  view: (episode?: string) => req<FixView>("GET", `${URL}${q(episode)}`),
  start: (episode: string | undefined, prompt: string, redo: boolean) => req<FixView>("POST", URL, { episode, prompt, redo }),
  apply: (episode: string | undefined, picks: { asset_id: string; credit: Found }[]) =>
    req<FixView>("POST", `${URL}/apply`, { episode, picks }),
  discard: (episode?: string) => req<FixView>("DELETE", `${URL}${q(episode)}`),
};
