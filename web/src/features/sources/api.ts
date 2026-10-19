import type { Episode } from "../../api";
import { failure } from "../../api";
import { PIECES_ABOVE, sendPieces } from "../upload-parts/pieces";

/** A recording the episode plays that is not on the server (lacuna_app/sources.py). */
export interface MissingSource {
  media_id: string;
  track: string;
  file: string;
  duration: number;
}

export const missingOf = (ep: Episode): MissingSource[] =>
  (ep as Episode & { missing_sources?: MissingSource[] }).missing_sources ?? [];

/** Upload one original file; the server matches it by content to a missing recording. */
export async function uploadSource(id: string, file: File, onProgress: (f: number) => void): Promise<Episode> {
  const q = new URLSearchParams({ name: file.name });
  // a raw track is hundreds of MB: in pieces first (upload-parts), then this request names them
  const part = file.size > PIECES_ABOVE ? await sendPieces(file, onProgress).done : "";
  if (part) q.set("part", part);
  const url = `/api/episodes/${encodeURIComponent(id)}/sources?${q}`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream" },
    body: part ? null : file,
  });
  if (!res.ok) throw await failure(res, url);
  return ((await res.json()) as { episode: Episode }).episode;
}
