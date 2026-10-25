// API of 用户条款和隐私政策 (lacuna_app/routes/legal.py); the current version comes with /api/auth/status
import { req } from "../../api";

export const legalApi = {
  agree: (version: string) => req<{ ok: true; agreed: string }>("POST", "/api/auth/agree", { version }),
};
