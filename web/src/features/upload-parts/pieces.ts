// Big files in pieces (lacuna_app/upload_parts.py): Cloudflare in front of the shared server
// refuses a request body over 100 MB, and a raw track is 1-2 GB.

/** Files above this go in pieces; smaller ones in one request, as before. */
export const PIECES_ABOVE = 48 * 1024 ** 2;
export const PIECE = 32 * 1024 ** 2;
/** Waits before each new try of a piece (seconds): about 2 minutes in all, enough to ride out a dropped
 *  Wi-Fi or the server restarting for an update. */
export const BACKOFF = [1, 2, 4, 8, 15, 30, 30, 30];

function newId(): string {
  const b = new Uint8Array(16);
  crypto.getRandomValues(b);
  return Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
}

/**
 * Send `file` as pieces to /api/uploads/parts; resolves with the id to pass as `part=` to the
 * endpoint that takes the file (its body then stays empty). A piece that fails is sent again
 * from the same offset, waiting longer each time (BACKOFF). `onProgress` gets 0..1 over the whole file.
 */
export function sendPieces(file: File, onProgress: (f: number) => void): { done: Promise<string>; abort: () => void } {
  const id = newId();
  let xhr: XMLHttpRequest | null = null;
  let aborted = false;
  const piece = (offset: number) =>
    new Promise<void>((resolve, reject) => {
      const x = new XMLHttpRequest();
      xhr = x;
      x.open("POST", `/api/uploads/parts?${new URLSearchParams({ id, offset: String(offset) })}`);
      x.setRequestHeader("Content-Type", "application/octet-stream");
      x.upload.onprogress = (e) => onProgress((offset + e.loaded) / file.size);
      x.onload = () => {
        if (x.status === 401) window.dispatchEvent(new Event("lacuna:auth"));
        if (x.status >= 200 && x.status < 300) return resolve();
        let detail: unknown = x.statusText || x.status;
        try {
          detail = JSON.parse(x.responseText).detail ?? detail;
        } catch {
          /* not JSON */
        }
        reject(Object.assign(new Error(String(detail)), { status: x.status }));
      };
      x.onerror = () => reject(new Error(x.statusText || "network error"));
      x.onabort = () => reject(new DOMException("aborted", "AbortError"));
      x.send(file.slice(offset, Math.min(offset + PIECE, file.size)));
    });
  const done = (async () => {
    for (let offset = 0; offset < file.size; offset += PIECE) {
      for (let attempt = 1; ; attempt++) {
        if (aborted) throw new DOMException("aborted", "AbortError");
        try {
          await piece(offset);
          break;
        } catch (e) {
          const status = (e as { status?: number }).status ?? 0;
          // a refusal (signed out, not allowed) won't change on a retry; a dropped connection may
          if (aborted || (status >= 400 && status < 500) || attempt > BACKOFF.length) throw e;
          await new Promise((r) => setTimeout(r, 1000 * BACKOFF[attempt - 1]));
        }
      }
    }
    onProgress(1);
    return id;
  })();
  return {
    done,
    abort: () => {
      aborted = true;
      xhr?.abort();
    },
  };
}
