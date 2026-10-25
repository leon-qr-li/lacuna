// An episode nobody opened for 14 days has its audio in cloud storage (lacuna_app/cold.py): opening it answers
// 423 while the server brings the audio back (10-30 s). `openEpisode` keeps asking until it is here, reporting
// the progress, so the page shows 「正在取回音频」 instead of an error.
import type { RequestError } from "../../api";

export interface Restoring {
  progress: number;
  failed: boolean;
}

export const restoringOf = (e: unknown): Restoring | null => (e as RequestError & { restoring?: Restoring }).restoring ?? null;

/** `load()` until it stops answering 423; `onRestoring` sees each progress report. `alive()` false: stop. */
export async function openEpisode<T>(load: () => Promise<T>, onRestoring: (r: Restoring) => void, alive: () => boolean,
  everyMs = 1500): Promise<T> {
  for (;;) {
    try {
      return await load();
    } catch (e) {
      const r = restoringOf(e);
      if (!r || r.failed || !alive()) throw e;
      onRestoring(r);
      await new Promise((ok) => window.setTimeout(ok, everyMs));
      if (!alive()) throw e;
    }
  }
}
