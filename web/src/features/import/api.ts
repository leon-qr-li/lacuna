import type { ImportJob } from "../../api";
import { req } from "../../api";

/** A raw track the server has (copied in from a drop, or picked): what the import form keeps. */
export interface PickedTrack {
  path: string;
  name: string;
  duration: number | null;
  size: number;
}

/** ImportJob plus the server's time-left estimate (lacuna_app/import_eta.py) while it runs. */
export type ImportJobView = ImportJob & { eta_s?: number | null };

/**
 * Send a dropped / picked file to the local app (127.0.0.1 only; it keeps a copy in the workspace).
 * XHR rather than fetch so a 1-2 GB WAV shows how far the copy is. `abort` cancels it.
 */
export function uploadTrack(file: File, onProgress: (f: number) => void): { done: Promise<PickedTrack>; abort: () => void } {
  const xhr = new XMLHttpRequest();
  const done = new Promise<PickedTrack>((resolve, reject) => {
    xhr.open("POST", `/api/imports/tracks?${new URLSearchParams({ name: file.name })}`);
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () => {
      let body: { track?: PickedTrack; detail?: unknown } = {};
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* not JSON */
      }
      if (xhr.status >= 200 && xhr.status < 300 && body.track) resolve(body.track);
      else reject(new Error(String(body.detail ?? xhr.statusText ?? xhr.status)));
    };
    xhr.onerror = () => reject(new Error(xhr.statusText || "network error"));
    xhr.onabort = () => reject(new DOMException("aborted", "AbortError"));
    xhr.send(file);
  });
  return { done, abort: () => xhr.abort() };
}

export const importApi = {
  imports: () => req<{ jobs: ImportJobView[]; next_id: string }>("GET", "/api/imports"),
  removeTrack: (path: string) => req<{ removed: boolean }>("POST", "/api/imports/tracks/remove", { path }),
};
