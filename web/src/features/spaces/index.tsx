import type { Feature } from "../registry";
import { SpaceSwitcher } from "./SpaceSwitcher";
import "./spaces.css";

// the workspace menu sits first in the top bar; the 工作区 card is in 设置 (SpacesCard)
export const feature: Feature = {
  nav: [{ order: -10, path: "spaces", render: () => <SpaceSwitcher />, on: ["home", "episode", "page"] }],
};
