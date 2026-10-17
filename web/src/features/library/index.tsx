import type { Feature } from "../registry";
import { LibraryView } from "./LibraryView";
import { MusicView } from "./MusicView";
import "./library.css";

export const feature: Feature = {
  pages: [{ path: "library", title: "素材库", render: () => <LibraryView /> }],
  tabs: [
    {
      mode: "music",
      label: "配乐",
      order: 30,
      render: ({ id, ep, pauseMain }) => <MusicView key={ep.version} id={id} onPauseMain={pauseMain} />,
    },
  ],
  nav: [
    {
      order: 10,
      path: "library",
      render: () => (
        <a className="btn btn-outline row" href="#/library">
          素材库
        </a>
      ),
      on: ["home", "episode", "page"],
    },
  ],
};
