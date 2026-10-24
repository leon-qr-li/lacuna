import { t } from "../../i18n";
import { useProjects } from "./api";

/** 节目设置, right on the show's 首页 next to its name (Leon 2026-10-24: the top-left menu alone was too hidden). */
export function SettingsLink() {
  const cur = useProjects()?.current;
  if (!cur || cur.sample) return null;
  return (
    <a className="btn btn-outline btn-small prj-settings-link" href="#/project" data-testid="home-project-settings">
      {t("节目设置")}
    </a>
  );
}
