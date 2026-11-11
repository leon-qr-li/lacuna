import { t } from "../../i18n";
import { useProjects } from "./api";

/** 节目设置 on the show's 首页, in the row after 导入新一集 (Leon 2026-10-24: the top-left menu alone was too
 *  hidden; batch 7 T3: one row of buttons). */
export function SettingsLink() {
  const cur = useProjects()?.current;
  if (!cur || cur.sample) return null;
  return (
    <a className="btn btn-outline prj-settings-link" href="#/project" data-testid="home-project-settings">
      {t("节目设置")}
    </a>
  );
}
