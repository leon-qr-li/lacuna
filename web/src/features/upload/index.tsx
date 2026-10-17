import type { Feature } from "../registry";
import { UploadView } from "./UploadView";
import "./upload.css";

export const feature: Feature = {
  tabs: [
    {
      mode: "upload",
      label: "上传喜马拉雅",
      order: 60,
      render: ({ id, ep, flash }) => <UploadView id={id} version={ep.version} flash={flash} />,
    },
  ],
};
