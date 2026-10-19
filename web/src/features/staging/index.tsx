import type { Feature } from "../registry";
import { StagingBadge } from "./StagingBadge";
import "./staging.css";

// the staging site (preview.<domain>, decision staging-site) says so in the top bar and the tab title
export const feature: Feature = {
  nav: [{ order: -20, path: "staging", render: () => <StagingBadge />, on: ["home", "episode", "page"] }],
};
