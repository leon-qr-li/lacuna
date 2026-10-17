import type { Feature } from "../registry";
import "./episodes.css";
import { t } from "../../i18n";

/** The episode overview (home) is `#/`, or no hash at all when the app first opens. */
const onHome = () => ["", "#", "#/"].includes(window.location.hash);

function EpisodesLink() {
  return (
    <a className="btn btn-outline row nav-episodes" href="#/" aria-current={onHome() ? "page" : undefined}>
      {t("剧集")}
    </a>
  );
}

export const feature: Feature = {
  nav: [{ order: 0, path: "", render: () => <EpisodesLink />, on: ["home", "episode", "page"] }],
};
