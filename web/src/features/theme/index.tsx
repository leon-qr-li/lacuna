import { useEffect, useState } from "react";
import type { Feature } from "../registry";
import { currentTheme, setTheme } from "./theme";
import "./theme.css";

function ThemeToggle() {
  const [theme, set] = useState(currentTheme);
  useEffect(() => {
    const on = () => set(currentTheme());
    window.addEventListener("lacuna-theme", on);
    return () => window.removeEventListener("lacuna-theme", on);
  }, []);
  const next = theme === "dark" ? "light" : "dark";
  const label = next === "dark" ? "切换到深色" : "切换到浅色";
  return (
    <button type="button" className="btn btn-ghost theme-toggle" onClick={() => setTheme(next)} title={label} aria-label={label} data-testid="theme-toggle">
      {theme === "dark" ? (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </svg>
      ) : (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" aria-hidden="true">
          <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
        </svg>
      )}
    </button>
  );
}

export const feature: Feature = {
  nav: [{ order: 90, path: "theme", render: () => <ThemeToggle />, on: ["home", "episode", "page"] }],
};
