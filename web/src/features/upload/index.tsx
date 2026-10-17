import type { Feature } from "../registry";
import { UploadView } from "./UploadView";
import "./upload.css";
import { t } from "../../i18n";

export const feature: Feature = {
  tabs: [
    {
      mode: "upload",
      label: t("上传喜马拉雅"),
      group: "publish",
      order: 60,
      render: ({ id, ep, flash }) => <UploadView id={id} version={ep.version} flash={flash} />,
    },
  ],
};
