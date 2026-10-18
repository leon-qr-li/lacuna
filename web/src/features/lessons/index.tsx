import type { Feature } from "../registry";
import { LessonsView } from "./LessonsView";
import "./lessons.css";
import { t } from "../../i18n";

/** 本集学到的规则 (首次检测 #12): a step of the episode flow between 声音 and 配乐 (order 20); runs only when he clicks 总结. */
export const feature: Feature = {
  tabs: [
    {
      mode: "lessons",
      label: t("本集学到的规则"),
      order: 20,
      render: ({ id, pauseMain }) => <LessonsView id={id} pauseMain={pauseMain} />,
    },
  ],
};
