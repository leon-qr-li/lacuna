import type { Feature } from "../registry";
import { TopLine } from "./Loading";

/** The shared loading pieces live in ./Loading; this entry only mounts the top line on every screen. */
export const feature: Feature = {
  nav: [{ order: 0, path: "loading", render: () => <TopLine />, on: ["home", "episode", "page"] }],
};
