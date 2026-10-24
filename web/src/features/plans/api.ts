// API of 套餐与用量 (lacuna_app/routes/plans.py)
import { req } from "../../api";
import type { PlanId } from "../auth/api";

export interface PlanLimits {
  id: PlanId;
  name: string;
  /** audio hours a month (the trial: once); null = unlimited */
  hours: number | null;
  hours_once: boolean;
  shows: number | null;
  /** people in a show besides the one who made it; null = unlimited */
  collaborators: number | null;
  hosts: number;
}

export interface MyPlan {
  plan: PlanId;
  /** given for free (Leon and Pei) */
  free: boolean;
  limits: PlanLimits;
  /** shows this account made */
  shows: number;
  /** counted from batch 5 on; null until then */
  hours_used: number | null;
  collaborators: { id: string; name: string; count: number }[];
  plans: PlanLimits[];
}

/** 「想要更多时长」 (lacuna_app/routes/hour_requests.py) */
export interface HourRequest {
  id: string;
  created: number;
  status: "new" | "approved" | "declined";
  hours: number;
  reason: string;
  granted: number | null;
}

export const plansApi = {
  mine: () => req<MyPlan>("GET", "/api/plan"),
  hours: () => req<{ requests: HourRequest[] }>("GET", "/api/plan/hours"),
  askHours: (hours: number, reason: string, would_pay: boolean) =>
    req<{ requests: HourRequest[] }>("POST", "/api/plan/hours", { hours, reason, would_pay }),
};
