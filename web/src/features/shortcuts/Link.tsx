import { t } from "../../i18n";
import "./shortcuts.css";

/** 「自定义快捷键」 at the foot of the "?" cards: opens 设置 → 快捷键. */
export function CustomizeLink() {
  return (
    <a className="sk-link" href="#/settings/keys" data-testid="customize-shortcuts">
      {t("自定义快捷键")} →
    </a>
  );
}
