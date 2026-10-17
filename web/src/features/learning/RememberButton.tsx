// 「记住」 next to 发送 in the AI producer chat: what is typed becomes a candidate rule as is,
// no need to start it with 「记住：」 (D: 2026-10-17-learn-from-chat-asks)
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
      title={t("把这句当成长期要求记下来（进「学到的规则」等你确认），不改这一期")}
      onClick={() => onSend((said, at) => learningApi.remember(epId, said, at))}
    >
      {t("记住")}
    </button>
  );
}
