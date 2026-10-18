import { navCurrent, type Feature } from "../registry";
import { LibraryView } from "./LibraryView";
import { MusicView } from "./MusicView";
import "./library.css";
import { t } from "../../i18n";

export const feature: Feature = {
  pages: [{ path: "library", title: t("素材库"), render: () => <LibraryView /> }],
  tabs: [
    {
      mode: "music",
      label: t("配乐"),
      order: 30,
      render: ({ id, ep, pauseMain }) => <MusicView key={ep.version} id={id} onPauseMain={pauseMain} />,
    },
  ],
  nav: [
    {
      order: 10,
      path: "library",
      render: () => (
        <a className="btn btn-outline row" href="#/library" aria-current={navCurrent("library")}>
          {t("素材库")}
        </a>
      ),
      on: ["home", "episode", "page"],
    },
  ],
};
