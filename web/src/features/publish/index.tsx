import type { Feature } from "../registry";
import { PublishView } from "./PublishView";
import "./publish.css";

export const feature: Feature = {
  tabs: [
    {
      mode: "publish",
      label: "发布资料",
      order: 40,
      render: ({ id, ep, flash }) => <PublishView id={id} version={ep.version} flash={flash} />,
    },
  ],
};
