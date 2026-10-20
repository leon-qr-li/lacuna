import type { Feature } from "../registry";
import { t } from "../../i18n";
import { useShow } from "./api";
import { ShowView } from "./ShowView";
import "./show.css";

/** No link any more (节目 is in 项目设置); loading the show here sets the host colours (--host-N) on every screen. */
function ShowLink() {
  useShow();
  return null;
}

// 节目设置 became 项目设置 (features/projects, #/project); an old #/show link opens it. The hidden
// loader stays so every screen gets the host colours.
export const feature: Feature = {
  pages: [{ path: "show", title: t("项目设置"), render: () => <ShowView /> }],
  nav: [{ order: 25, path: "show", render: () => <ShowLink />, on: ["home", "episode", "page"] }],
};
