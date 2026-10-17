// API of this feature (moved out of src/api.ts so features don't all edit one file)
import type { ChatReply } from "../../api";
import { req } from "../../api";

export interface LearnedRule {
  id: string;
  kind: string;
  title: string;
  detail: string;
  prompt: string;
  key: Record<string, string | number>;
  evidence: Record<string, unknown>;
  examples: { text: string; raw: [number, number] | null; verdict: string; episode: string; reason: string }[];
  policy: { review?: boolean; confidence?: number } | null;
  state: "candidate" | "approved" | "rejected";
  updated: boolean;
  stale?: boolean;
  approved_at: string | null;
}

export interface LearningOverview {
  rules: LearnedRule[];
  pending: number;
  stats: {
    episodes: string[];
    decisions: number;
    considered: number;
    kept: number;
    restored: number;
    accepted: number;
    declined: number;
    added: number;
    untouched: number;
  };
}


export const learningApi = {
  learning: () => req<LearningOverview>("GET", "/api/learning"),
  decideRule: (id: string, action: "approve" | "reject" | "reset") =>
    req<LearningOverview>("POST", "/api/learning/rules", { id, action }),
  remember: (episodeId: string, text: string, playhead: number) =>
    req<ChatReply>("POST", `/api/episodes/${encodeURIComponent(episodeId)}/remember`, { text, playhead }),
};
