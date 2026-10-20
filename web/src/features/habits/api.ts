// The editor's own habits (lacuna_app/habits.py, routes/habits.py): 剪辑力度 follows the person into every project.
import { req } from "../../api";
import type { CutLevel } from "../show/api";

export const habitsApi = {
  get: () => req<{ cut_level: CutLevel }>("GET", "/api/habits"),
  setLevel: (cut_level: CutLevel) => req<{ cut_level: CutLevel }>("PUT", "/api/habits", { cut_level }),
};
