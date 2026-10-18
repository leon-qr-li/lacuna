import type { Feature } from "../registry";
import { LevelsView } from "./LevelsView";
import "./levels.css";
import { t } from "../../i18n";

/** 声音: both hosts at one loudness (done at import), per-track gain, clipped spots (backlog 7). */
export const feature: Feature = {
  tabs: [
    {
      mode: "levels",
      label: t("声音"),
      order: 15,
      render: ({ id, ep, flash, pauseMain, onEpisode }) => (
        <LevelsView
          id={id}
          ep={ep}
          flash={flash}
          onPauseMain={pauseMain}
          onEpisode={onEpisode}
        />
      ),
    },
  ],
};
