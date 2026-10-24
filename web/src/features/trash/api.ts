// API of the 回收区 (lacuna_app/routes/trash.py): deleted shows and accounts, kept 60 days.
import { req } from "../../api";

export interface TrashItem {
  kind: "show" | "user";
  /** a show: its place in the 回收区; an account: its email */
  id: string;
  name: string;
  by: string | null;
  /** seconds since 1970 */
  deleted_at: number;
  left_days: number;
}

export interface TrashList {
  items: TrashItem[];
  keep_days: number;
}

export const trashApi = {
  list: () => req<TrashList>("GET", "/api/site/trash"),
  restore: (x: TrashItem) =>
    req<TrashList>("POST", `/api/site/trash/${x.kind}/${encodeURIComponent(x.id)}/restore`),
};
