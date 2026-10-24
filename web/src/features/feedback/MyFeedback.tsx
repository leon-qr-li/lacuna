import { useEffect, useState } from "react";
import { locale, t } from "../../i18n";
import { feedbackApi, type Kind, type Mine, type Status } from "./api";
import { setUnread } from "./unread";

export const KIND_LABEL: Record<Kind, string> = { bug: t("问题"), idea: t("想法"), praise: t("夸一句") };
export const STATUS_LABEL: Record<Status, string> = {
  received: t("已收到"),
  working: t("在处理"),
  planned: t("在计划中"),
  fixed: t("已修好"),
  shipped: t("已上线"),
  declined: t("暂不做"),
};
const STATUS_TONE: Record<Status, string> = {
  received: "chip-plain",
  working: "",
  planned: "",
  fixed: "chip-ok",
  shipped: "chip-ok",
  declined: "chip-warn",
};

const day = (s: number) => new Date(s * 1000).toLocaleDateString(locale, { month: "short", day: "numeric" });

/** 我的反馈: what the person sent, its status and the site owner's answers. Looking marks the answers read. */
export function MyFeedback({ onWrite }: { onWrite?: () => void }) {
  const [items, setItems] = useState<Mine[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    feedbackApi.mine().then(
      (r) => {
        setItems(r.items);
        if (r.unread) feedbackApi.seen().then((s) => setUnread(s.unread), () => undefined);
      },
      (e) => setErr((e as Error).message),
    );
  }, []);
  if (err) return <p className="error small">{err}</p>;
  if (!items) return <p className="muted small">{t("正在读取…")}</p>;
  return (
    <div className="fb-mine" data-testid="feedback-mine">
      {items.length === 0 && (
        <div className="fb-empty">
          <p className="muted">{t("你还没有发过反馈。遇到问题、有想法，随时点右上角的「反馈」告诉我们。")}</p>
          {onWrite && (
            <button type="button" className="btn btn-outline btn-small" onClick={onWrite}>
              {t("写新反馈")}
            </button>
          )}
        </div>
      )}
      {items.map((m) => (
        <article key={m.id} className={`fb-item${m.unread ? " is-new" : ""}`} data-testid="feedback-item">
          <div className="fb-item-head">
            <span className="chip chip-plain">{KIND_LABEL[m.kind]}</span>
            <b className="fb-item-text">{m.text}</b>
            <span className={`chip ${STATUS_TONE[m.status]}`} data-testid="feedback-status">
              {STATUS_LABEL[m.status]}
            </span>
          </div>
          <div className="muted small">
            {[day(m.created), m.show?.name, m.shot ? t("有截图") : null].filter(Boolean).join(" · ")}
          </div>
          {m.replies.map((r, i) => (
            <div key={i} className="fb-reply" data-testid="feedback-reply">
              <span className="small fb-reply-who">
                {t("站长回复")}
                {m.unread && i === m.replies.length - 1 && <span className="fb-new">{t("新")}</span>}
              </span>
              <p>{r.text}</p>
            </div>
          ))}
          {m.adopted && (
            <p className="small fb-adopted" data-testid="feedback-adopted">
              {t("已采纳，本月送你 {n} 小时剪辑时长", { n: m.bonus_hours || 1 })}
            </p>
          )}
        </article>
      ))}
      {items.length > 0 && (
        <p className="muted small fb-legend">{t("状态：已收到 → 在处理 / 在计划中 → 已修好 / 已上线；暂不做的会写原因。")}</p>
      )}
    </div>
  );
}
