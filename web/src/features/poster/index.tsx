import type { Feature } from "../registry";
import { PosterView } from "./PosterView";
import "./poster.css";

export const feature: Feature = {
  tabs: [
    {
      mode: "poster",
      label: "海报",
      order: 50,
      render: ({ id, flash, pauseMain }) => <PosterView id={id} flash={flash} onPauseMain={pauseMain} />,
    },
  ],
};
