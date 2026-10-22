import type { Feature } from "../registry";
import { LessonsView } from "./LessonsView";
import "./lessons.css";
import { t } from "../../i18n";

/** 本集学到的规则 (首次检测 #12): not a step of the flow (new-user batch Q8); 整集试听 links here. Runs only on 总结. */
export const feature: Feature = {
  tabs: [
    {
      mode: "lessons",
      label: t("本集学到的规则"),
      order: 20,
      offFlow: true,
      render: ({ id, pauseMain }) => <LessonsView id={id} pauseMain={pauseMain} />,
    },
  ],
};
