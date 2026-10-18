// 「记住」 next to 发送 in the AI producer chat: LACUNA rewrites what is typed into a rule and asks
// before storing it (features/lessons/RememberCard.tsx); no need to start it with 「记住：」
import type { ChatReply } from "../../api";
import { t } from "../../i18n";
import { learningApi } from "./api";

export type Ask = (said: string, at: number) => Promise<ChatReply>;

export function RememberButton({ epId, disabled, onSend }: { epId: string; disabled: boolean; onSend: (ask: Ask) => void }) {
  return (
    <button
      type="button"
      className="btn btn-outline"
      disabled={disabled}
      title={t("让 LACUNA 把这句整理成一条长期规则，你确认后才记住；不改这一期")}
      onClick={() => onSend((said, at) => learningApi.remember(epId, said, at))}
    >
      {t("记住")}
    </button>
  );
}
