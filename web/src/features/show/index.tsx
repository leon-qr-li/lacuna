import type { Feature } from "../registry";
import { navCurrent } from "../registry";
import { t } from "../../i18n";
import { useShow } from "./api";
import { ShowView } from "./ShowView";
import "./show.css";

/** Top-bar link to 节目; loading the show here also sets the host colours (--host-N) on every screen. */
function ShowLink() {
  const show = useShow();
  if (!show) return null;
  return (
    <a className="btn btn-outline row" href="#/show" aria-current={navCurrent("show")} data-testid="show-link">
      {t("节目")}
    </a>
  );
}

export const feature: Feature = {
  pages: [{ path: "show", title: t("节目设置"), render: () => <ShowView /> }],
  nav: [{ order: 25, path: "show", render: () => <ShowLink />, on: ["home", "episode", "page"] }],
};
