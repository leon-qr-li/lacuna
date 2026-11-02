// API of 自定义快捷键 (lacuna_app/routes/shortcuts.py): the keys this person changed, action id -> keys.
import { req } from "../../api";

export const shortcutsApi = {
  get: () => req<{ keys: Record<string, string[]> }>("GET", "/api/shortcuts"),
  put: (keys: Record<string, string[]>) => req<{ keys: Record<string, string[]> }>("PUT", "/api/shortcuts", { keys }),
};
