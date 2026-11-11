// Upload with progress (Leon 2026-10-31, 配乐上传进度条): fetch() cannot report how much of a request body has
// gone, so one-request uploads go through XMLHttpRequest. Big files go in pieces first (upload-parts), which
// report their own progress.
import { failure } from "../../api";
import { t } from "../../i18n";

/** f: 0..1 of the file sent; "work": every byte is on the server, which is now reading the file. */
export type OnProgress = (f: number, phase: "send" | "work") => void;

/** POST `body` (raw bytes) to `url` and resolve with the JSON answer; errors read like `req`'s. */
export function postWithProgress<T>(url: string, body: Blob | null, onProgress?: OnProgress): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open("POST", url);
    x.setRequestHeader("Content-Type", "application/octet-stream");
    x.upload.onprogress = (e) => {
      if (e.lengthComputable && e.total) onProgress?.(e.loaded / e.total, "send");
    };
    x.upload.onload = () => onProgress?.(1, "work");
    x.onload = () => {
      if (x.status >= 200 && x.status < 300) {
        try {
          resolve(JSON.parse(x.responseText) as T);
        } catch {
          reject(new Error(t("服务器的回答读不懂，请再试一次")));
        }
        return;
      }
      const res = new Response(x.responseText || null, { status: x.status || 500, statusText: x.statusText });
      void failure(res, url).then(reject, reject);
    };
    x.onerror = () => reject(new Error(t("网络断了，文件没有传完，请再试一次")));
    x.onabort = () => reject(new DOMException("aborted", "AbortError"));
    x.send(body);
  });
}
