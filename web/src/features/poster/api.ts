// API of this feature (moved out of src/api.ts so features don't all edit one file)
import { ep, req } from "../../api";

export interface PosterVariant {
  id: string;
  direction: string;
  direction_label: string;
  name: string;
  concept: string;
  parent: string | null;
  instruction: string | null;
  notes: string[];
  created_at: string;
  cost_usd: number | null;
}

export interface PosterCover {
  variant: string;
  px: number;
  folder: string;
  jpg: string;
  png: string;
  jpg_bytes: number;
  png_bytes: number;
  rendered_at: string;
}

export interface PosterJob {
  kind: "generate" | "revise" | "choose";
  state: "running" | "done" | "error";
  stage: string;
  started: number;
  finished: number | null;
  error: string | null;
}

export interface PosterView {
  variants: PosterVariant[];
  chosen: string | null;
  cover: PosterCover | null;
  errors: string[];
  job: PosterJob | null;
  has_pack: boolean;
  available: boolean; // Claude reachable (API key + SDK)
  directions: { key: string; label: string }[];
}


export const posterApi = {
  poster: (id: string) => req<PosterView>("GET", `${ep(id)}/poster`),
  generatePoster: (id: string) => req<PosterView>("POST", `${ep(id)}/poster/generate`),
  revisePoster: (id: string, v: string, instruction: string) =>
    req<PosterView>("POST", `${ep(id)}/poster/${v}/revise`, { instruction }),
  choosePoster: (id: string, v: string) => req<PosterView>("POST", `${ep(id)}/poster/${v}/choose`),
  posterPreview: (id: string, v: string) => `${ep(id)}/poster/${v}.png`,
};
