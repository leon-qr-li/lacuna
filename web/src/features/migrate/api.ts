// API of moving the desktop workspace to the cloud (lacuna_app/routes/migrate.py)
import { failure, req } from "../../api";
import { PIECES_ABOVE, sendPieces } from "../upload-parts/pieces";

export interface MigrateState {
  /** files already on the server from an earlier try: path → size */
  staged: Record<string, number>;
  episodes: number;
}

export interface MigrateResult {
  files: number;
  bytes: number;
  episodes: number;
  restarting: boolean;
}

// never copied (the server's own accounts, workspaces, models; scratch): lacuna_app/migrate.py
const SKIP_TOP = new Set(["auth", "spaces", "models", "tmp"]);
const SKIP_NAMES = new Set(["desktop.ini", "Thumbs.db", ".DS_Store"]);

/** The file's path inside the picked folder, or null for one that is never copied. */
export function relPath(f: File): string | null {
  const parts = (f.webkitRelativePath || f.name).split(/[\\/]/).filter(Boolean);
  const rel = parts.length > 1 ? parts.slice(1) : parts;     // drop the picked folder's own name
  if (!rel.length || SKIP_TOP.has(rel[0]) || SKIP_NAMES.has(rel[rel.length - 1])) return null;
  return rel.join("/");
}

export const migrateApi = {
  /** null when this isn't offered (desktop, not the owner, not the main workspace) */
  state: async (): Promise<MigrateState | null> => {
    const r = await fetch("/api/migrate");
    return r.ok ? ((await r.json()) as MigrateState) : null;
  },
  finish: (files: number, bytes: number) => req<MigrateResult>("POST", "/api/migrate/finish", { files, bytes }),
  cancel: () => req<{ ok: boolean }>("POST", "/api/migrate/cancel"),
};

/** Send one file; big ones in pieces. `onProgress` gets the bytes sent so far. */
export function sendFile(rel: string, file: File, onProgress: (sent: number) => void): { done: Promise<void>; abort: () => void } {
  const ctl = new AbortController();
  let pieces: { abort: () => void } | null = null;
  const done = (async () => {
    let part = "";
    let body: Blob | undefined = file;
    if (file.size > PIECES_ABOVE) {
      const p = sendPieces(file, (f) => onProgress(f * file.size));
      pieces = p;
      part = await p.done;
      body = undefined;
    }
    const url = `/api/migrate/file?${new URLSearchParams({ path: rel, part })}`;
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: body ?? new Blob([]),
      signal: ctl.signal,
    });
    if (!res.ok) throw await failure(res, url);
    onProgress(file.size);
  })();
  return {
    done,
    abort: () => {
      ctl.abort();
      pieces?.abort();
    },
  };
}

/** After the move the server restarts; resolves once it answers again. */
export async function waitBack(timeoutMs = 180_000): Promise<boolean> {
  const until = Date.now() + timeoutMs;
  await new Promise((r) => setTimeout(r, 2000));
  while (Date.now() < until) {
    try {
      const r = await fetch("/api/health", { cache: "no-store" });
      if (r.ok) return true;
    } catch {
      /* still restarting */
    }
    await new Promise((r) => setTimeout(r, 2000));
  }
  return false;
}
