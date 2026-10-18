import type { Feature } from "../registry";
import { XimalayaView } from "./XimalayaView";
import "./ximalaya.css";
import { t } from "../../i18n";

export const feature: Feature = {
  tabs: [
    {
      mode: "ximalaya",
      label: t("喜马拉雅版"),
      group: "publish",
      order: 45,
      render: ({ id, ep, flash }) => <XimalayaView id={id} version={ep.version} flash={flash} />,
    },
  ],
};
