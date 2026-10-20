import { t } from "../../i18n";
import "./chat-dock.css";

/** Where the AI 制作人 panel opens and closes (Leon 2026-10-20): 「收起 »」 on the panel itself, and a
 * floating 「AI 制作人」 button at the bottom right while it is closed, so the editor gets the full width. */

const CHAT = "M21 12a8 8 0 0 1-11.6 7.1L4 20.5l1.4-4.9A8 8 0 1 1 21 12z";
const CHEVS = "M7 6l6 6-6 6M13 6l6 6-6 6";

function Svg({ d, size = 16 }: { d: string; size?: number }) {
  return (
    <svg className="ic" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  );
}

export function ChatCollapse({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" className="chat-collapse" onClick={onClick} title={t("收起 AI 制作人")} aria-label={t("收起")} data-testid="chat-collapse">
      <span className="chat-collapse-label">{t("收起")}</span> <Svg d={CHEVS} size={14} />
    </button>
  );
}

export function ChatFab({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" className="chat-fab" onClick={onClick} data-testid="chat-open">
      <Svg d={CHAT} size={18} /> {t("AI 制作人")}
    </button>
  );
}
