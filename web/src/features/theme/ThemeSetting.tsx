import { useEffect, useState } from "react";
import { savedTheme, setTheme } from "./theme";
import { lang, setLang, t } from "../../i18n";

// each language is named in itself, so it can be found from either interface
const langs = [
  ["zh", "中文"], // i18n-ignore
  ["en", "English"],
] as const;

/** 设置 → 外观: theme (light / dark / follow the system) and the interface language. */
export function ThemeSetting() {
  const [choice, setChoice] = useState(() => savedTheme() ?? "system");
  useEffect(() => {
    const on = () => setChoice(savedTheme() ?? "system");
    window.addEventListener("lacuna-theme", on);
    return () => window.removeEventListener("lacuna-theme", on);
  }, []);
  const opts = [
    ["light", t("浅色")],
    ["dark", t("深色")],
    ["system", t("跟随系统")],
  ] as const;
  return (
    <section className="card" aria-label={t("外观")}>
      <h2>{t("外观")}</h2>
      <div className="set-row">
        <div>
          <strong>{t("主题")}</strong>
          <p className="muted small">{t("跟随系统：电脑切到深色时这里也变深色。")}</p>
        </div>
        <div className="seg" role="radiogroup" aria-label={t("主题")}>
          {opts.map(([v, label]) => (
            <button
              key={v}
              type="button"
              role="radio"
              aria-checked={choice === v}
              className={choice === v ? "is-on" : ""}
              onClick={() => setTheme(v === "system" ? null : v)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <div className="set-row">
        <div>
          <strong>{t("界面语言")}</strong>
          <p className="muted small">{t("切换后页面会刷新。节目内容（转写、show notes）仍是中文。")}</p>
        </div>
        <div className="seg" role="radiogroup" aria-label={t("界面语言")}>
          {langs.map(([v, label]) => (
            <button key={v} type="button" role="radio" aria-checked={lang === v} className={lang === v ? "is-on" : ""} onClick={() => lang !== v && setLang(v)}>
              {label}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
