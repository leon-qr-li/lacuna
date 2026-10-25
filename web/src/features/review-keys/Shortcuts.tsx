import { t } from "../../i18n";
import { help } from "./keys";
import "./review-keys.css";

/** The "?" button in the review dock and the shortcut card it opens. */
export function ShortcutsButton({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  return (
    <span className="rk-wrap">
      <button
        type="button"
        className="btn btn-ghost btn-round rk-btn"
        aria-expanded={open}
        aria-label={t("快捷键")}
        title={t("快捷键（?）")}
        onClick={onToggle}
      >
        ?
      </button>
      {open && (
        <div className="rk-card" role="dialog" aria-label={t("快捷键")} data-testid="review-shortcuts">
          <strong className="small">{t("快捷键")}</strong>
          <ul>
            {help().map((h) => (
              <li key={h.label}>
                <span className="rk-keys">
                  {h.keys.map((k) => (
                    <kbd key={k}>{k}</kbd>
                  ))}
                </span>
                <span>{h.label}</span>
              </li>
            ))}
          </ul>
          <p className="muted small">{t("在输入框里打字时快捷键不生效。")}</p>
        </div>
      )}
    </span>
  );
}

/** "已过目 37 / 114" in the dock, so progress stays in sight while scrolling the words. */
export function DockProgress({ done, total }: { done: number; total: number }) {
  return (
    <span className="rk-progress small" data-testid="dock-progress" title={t("已审阅 {done} / {n}", { done, n: total })}>
      {t("已审阅")} <strong>{done}</strong> / {total}
    </span>
  );
}
