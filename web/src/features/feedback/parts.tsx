// Small pieces other screens use: the top-bar button, 「告诉我们」 on an error, a new show's questions.
import { t } from "../../i18n";
import { openFeedback } from "./bus";
import { useSignedIn, useUnread } from "./unread";

/** 反馈 in the top bar, with a red dot when the site owner answered something not looked at yet. */
export function FeedbackButton() {
  const on = useSignedIn();
  return on ? <Button /> : null;
}

function Button() {
  const unread = useUnread();
  return (
    <button
      type="button"
      className="btn btn-outline row fb-btn"
      onClick={() => openFeedback(unread ? { mine: true } : {})}
      data-testid="feedback-open"
      aria-label={unread ? t("反馈（有新回复）") : t("反馈")}
    >
      {t("反馈")}
      {unread > 0 && <span className="fb-dot" data-testid="feedback-dot" />}
    </button>
  );
}

/** 「告诉我们」 next to an error: opens the panel with the error filled in (design A3). */
export function TellUs({ title, message, code }: { title: string; message?: string | null; code?: string }) {
  if (!useSignedIn()) return null;
  return (
    <button
      type="button"
      className="fb-tellus"
      onClick={(e) => {
        // it can sit inside a file picker's label: only this button
        e.preventDefault();
        e.stopPropagation();
        openFeedback({ kind: "bug", source: "error", error: { title, message: message ?? undefined, code } });
      }}
      data-testid="feedback-tellus"
    >
      {t("告诉我们")}
    </button>
  );
}

export const REGIONS: { id: string; label: string }[] = [
  { id: "na", label: t("北美") },
  { id: "eu", label: t("欧洲") },
  { id: "oceania", label: t("澳洲 / 新西兰") },
  { id: "asia", label: t("亚洲其他地区") },
  { id: "cn", label: t("中国大陆") },
];
export const EDITING: { id: string; label: string }[] = [
  { id: "self", label: t("自己用软件剪") },
  { id: "hired", label: t("找人剪") },
  { id: "none", label: t("基本不剪") },
  { id: "new", label: t("第一次做播客") },
];

export interface ShowAnswers {
  region?: string;
  editing?: string;
}

/** 让我们更了解你的节目 (design A7): asked in a new show's first setup (its name, language and hosts), both
 *  optional, seen only by the site owner. The show's language is the setup's own field, so it isn't asked twice. */
export function ShowQuestions({ value, onChange }: { value: ShowAnswers; onChange: (v: ShowAnswers) => void }) {
  const row = (key: keyof ShowAnswers, label: string, opts: { id: string; label: string }[]) => (
    <div className="fb-q">
      <span className="fb-label">{label}</span>
      <div className="fb-kinds">
        {opts.map((o) => (
          <button
            key={o.id}
            type="button"
            className={`fb-chip small${value[key] === o.id ? " on" : ""}`}
            aria-pressed={value[key] === o.id}
            onClick={() => onChange({ ...value, [key]: value[key] === o.id ? undefined : o.id })}
            data-testid={`show-q-${key}-${o.id}`}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
  return (
    <fieldset className="fb-showq" data-testid="show-questions">
      <legend>
        <b>{t("让我们更了解你的节目")}</b> <span className="small muted">{t("可跳过 · 只有站长能看到")}</span>
      </legend>
      {row("region", t("你和你的听众主要在哪？"), REGIONS)}
      {row("editing", t("你现在怎么剪辑？"), EDITING)}
    </fieldset>
  );
}
