/** Light / dark theme. The choice ("light" | "dark", or none = follow the system) is kept in
 *  localStorage; index.html applies it before first paint so there is no flash. */
export type Theme = "light" | "dark";
const KEY = "lacuna.theme";
const media = () => window.matchMedia?.("(prefers-color-scheme: dark)");

export function savedTheme(): Theme | null {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : null;
  } catch {
    return null;
  }
}

export function currentTheme(): Theme {
  return savedTheme() ?? (media()?.matches ? "dark" : "light");
}

export function applyTheme(): void {
  document.documentElement.dataset.theme = currentTheme();
}

export function setTheme(t: Theme | null): void {
  try {
    if (t) localStorage.setItem(KEY, t);
    else localStorage.removeItem(KEY);
  } catch {
    /* private mode: still switch for this page */
  }
  applyTheme();
  window.dispatchEvent(new Event("lacuna-theme"));
}

applyTheme();
media()?.addEventListener?.("change", () => savedTheme() || applyTheme());
