import type { Feature } from "../registry";
import "./episodes.css";
import { t } from "../../i18n";
import { ArchiveView } from "./ArchiveView";

/** The episode overview (home) is `#/`, or no hash at all when the app first opens. */
const onHome = () => ["", "#", "#/"].includes(window.location.hash);

function EpisodesLink() {
  return (
    <a className="btn btn-outline row nav-episodes" href="#/" aria-current={onHome() ? "page" : undefined}>
      {t("首页")}
    </a>
  );
}

export const feature: Feature = {
  nav: [{ order: 0, path: "", render: () => <EpisodesLink />, on: ["home", "episode", "page"] }],
  // 已归档: reached from the link under the episode list (no top-bar link of its own)
  pages: [{ path: "archive", title: t("已归档"), render: () => <ArchiveView /> }],
};
