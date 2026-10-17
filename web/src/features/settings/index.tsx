import type { Feature } from "../registry";
import { SettingsLink, SettingsView } from "./SettingsView";
import "./settings.css";

export const feature: Feature = {
  pages: [{ path: "settings", title: "设置", render: () => <SettingsView /> }],
  nav: [{ order: 30, path: "settings", render: () => <SettingsLink />, on: ["home"] }],
};
