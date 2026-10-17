import type { Feature } from "../registry";
import { PublishView } from "./PublishView";
import "./publish.css";
import { t } from "../../i18n";

export const feature: Feature = {
  tabs: [
    {
      mode: "publish",
      label: t("发布资料"),
      group: "publish",
      order: 40,
      render: ({ id, ep, flash }) => <PublishView id={id} version={ep.version} flash={flash} />,
    },
  ],
};
