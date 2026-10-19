import { useEffect, useState } from "react";
import { spacesApi, type Spaces } from "./api";
import { t } from "../../i18n";

/** Top bar: which workspace you are in; a menu to switch when you belong to more than one. */
export function SpaceSwitcher() {
  const [sp, setSp] = useState<Spaces | null>(null);
  useEffect(() => {
    spacesApi.list().then(setSp, () => setSp(null));
  }, []);
  if (!sp?.current || sp.mine.length < 2) return null;
  return (
    <label className="space-switch" title={t("工作区")}>
      <span className="sr-only">{t("工作区")}</span>
      <select
        value={sp.current.id}
        aria-label={t("工作区")}
        data-testid="space-switch"
        onChange={async (e) => {
          await spacesApi.switchTo(e.target.value);
          // everything on screen belongs to the old workspace: start fresh on 剧集
          window.location.hash = "#/";
          window.location.reload();
        }}
      >
        {sp.mine.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name}
          </option>
        ))}
      </select>
    </label>
  );
}
