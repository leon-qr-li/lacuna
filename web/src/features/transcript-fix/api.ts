// Transcript proofreading against the show's names (decision transcript-terms; lacuna_app/routes/transcript_fix.py)
import type { Episode } from "../../api";
import { ep, req } from "../../api";

export interface TermFix {
  wrong: string;
  right: string;
  count: number;
}
export type Proofread = Episode & { fixes: TermFix[]; changed: number; ai: boolean };

export const transcriptFixApi = {
  fix: (id: string, playhead: number) => req<Proofread>("POST", `${ep(id)}/transcript/fix`, { playhead }),
};

/** Changes whenever the transcript's words were proofread again (so cached transcript chunks reload). */
export const transcriptRev = (e: Episode) => (e as Episode & { transcript_rev?: string }).transcript_rev ?? "";
