import type { Feature } from "../registry";
import { PosterView } from "./PosterView";
import "./poster.css";
import { t } from "../../i18n";

export const feature: Feature = {
  tabs: [
    {
      mode: "poster",
      label: t("封面"),
      group: "publish",
      order: 50,
      render: ({ id, flash, pauseMain }) => <PosterView id={id} flash={flash} onPauseMain={pauseMain} />,
    },
  ],
};
