import { useEffect, useState } from "react";
import { savedTheme, setTheme } from "./theme";

/** 设置 → 外观: theme (light / dark / follow the system) and, later, the interface language. */
export function ThemeSetting() {
  const [choice, setChoice] = useState(() => savedTheme() ?? "system");
  useEffect(() => {
    const on = () => setChoice(savedTheme() ?? "system");
    window.addEventListener("lacuna-theme", on);
    return () => window.removeEventListener("lacuna-theme", on);
  }, []);
  const opts = [
    ["light", "浅色"],
    ["dark", "深色"],
    ["system", "跟随系统"],
  ] as const;
  return (
    <section className="card" aria-label="外观">
      <h2>外观</h2>
      <div className="set-row">
        <div>
          <strong>主题</strong>
          <p className="muted small">跟随系统：电脑切到深色时这里也变深色。</p>
        </div>
        <div className="seg" role="radiogroup" aria-label="主题">
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
          <strong>界面语言</strong>
          <p className="muted small">英文界面之后支持。</p>
        </div>
        <div className="seg" role="radiogroup" aria-label="界面语言">
          <button type="button" role="radio" aria-checked className="is-on">
            中文
          </button>
          <button type="button" role="radio" aria-checked={false} disabled>
            English
          </button>
        </div>
      </div>
    </section>
  );
}
