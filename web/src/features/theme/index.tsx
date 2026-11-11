import { useEffect, useState } from "react";
import type { Feature } from "../registry";
import { currentTheme, setTheme } from "./theme";
import { ThemeGlyph } from "./Glyph";
import "./theme.css";
import { t } from "../../i18n";

function ThemeToggle() {
  const [theme, set] = useState(currentTheme);
  useEffect(() => {
    const on = () => set(currentTheme());
    window.addEventListener("lacuna-theme", on);
    return () => window.removeEventListener("lacuna-theme", on);
  }, []);
  const next = theme === "dark" ? "light" : "dark";
  const label = next === "dark" ? t("切换到深色") : t("切换到浅色");
  return (
    <button type="button" className="btn btn-ghost theme-toggle" onClick={() => setTheme(next)} title={label} aria-label={label} data-testid="theme-toggle">
      <ThemeGlyph theme={theme} />
    </button>
  );
}

export const feature: Feature = {
  nav: [{ order: 90, path: "theme", render: () => <ThemeToggle />, on: ["home", "episode", "page"] }],
};
