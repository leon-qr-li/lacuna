// The last steps in the app, attached to a 遇到问题 report so nobody has to ask "what did you click?".
// Pages opened, changes sent to the server (method, path, status) and errors; never what was typed,
// never a response body. Kept in memory only, for this tab.
const MAX = 20;
const steps: string[] = [];
let lastError: string | null = null;

const clock = () => new Date().toTimeString().slice(0, 8);
const add = (s: string) => {
  steps.push(`${clock()} ${s}`);
  if (steps.length > MAX) steps.shift();
};

export const trail = () => [...steps];
export const lastFailure = () => lastError;

let installed = false;
/** Start listening (once, when the feature loads). */
export function installTrail() {
  if (installed || typeof window === "undefined") return;
  installed = true;
  add(`open ${location.hash || "#/"}`);
  window.addEventListener("hashchange", () => add(`open ${location.hash || "#/"}`));
  window.addEventListener("error", (e) => {
    lastError = String(e.message || "error").slice(0, 200);
    add(`script error: ${lastError}`);
  });
  window.addEventListener("unhandledrejection", (e) => {
    const r = e.reason as { message?: string } | undefined;
    lastError = String(r?.message ?? r ?? "error").slice(0, 200);
    add(`unhandled: ${lastError}`);
  });
  const raw = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const method = (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const path = url.replace(location.origin, "").split("?")[0];
    try {
      const res = await raw(input, init);
      // reads are too many to be useful; failed reads and every change are kept
      if (path.startsWith("/api/") && !path.startsWith("/api/feedback") && (method !== "GET" || !res.ok)) {
        add(`${method} ${path} → ${res.status}`);
        if (!res.ok) lastError = `${method} ${path} → ${res.status}`;
      }
      return res;
    } catch (e) {
      if (path.startsWith("/api/")) {
        add(`${method} ${path} → network error`);
        lastError = `${method} ${path} → network error`;
      }
      throw e;
    }
  };
}
