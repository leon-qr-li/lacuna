import type { Feature } from "../registry";
import { OnboardTag } from "./Checklist";
import "./onboarding.css";

/** 入门 (new-user batch): welcome page, 入门清单, LACUNA 示例节目 and its coach. The home card, welcome page and
 *  coach are placed by Home.tsx / App.tsx; the top-bar tag "入门 2/6" is here. */
export const feature: Feature = {
  nav: [{ order: 5, path: "", render: () => <OnboardTag />, on: ["episode", "page"] }],
};
