import type { Feature } from "../registry";
import { UploadBadge } from "./UploadBadge";
import "./import.css";

// the tracks keep uploading on every page (draft.ts): the top bar says how far they are
export const feature: Feature = {
  nav: [{ order: -10, path: "upload-progress", render: () => <UploadBadge />, on: ["home", "episode", "page"] }],
};
