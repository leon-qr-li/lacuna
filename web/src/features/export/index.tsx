import { ExportPanel } from "../../components/ExportPanel";
import type { Feature } from "../registry";
import "./export.css";

/** 导出 as a step of the episode flow, between 配乐 and 发布 (phase 8). */
export const feature: Feature = {
  tabs: [
    {
      mode: "export",
      label: "导出",
      order: 35,
      render: ({ id, ep }) => (
        <main className="export-step">
          <ExportPanel id={id} version={ep.version} inline />
        </main>
      ),
    },
  ],
};
