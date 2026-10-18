// 「记住」 in the AI producer chat (首次检测 #9): LACUNA says how it read the ask; it becomes a rule only
// after 记住这条. 改一下 tells LACUNA what to change (typed or by voice), 不用 stores nothing.
import { useState } from "react";
import { t } from "../../i18n";
import { BusyLabel } from "../loading/Loading";
import type { RememberDraft } from "./api";
import { lessonsApi } from "./api";
import { TalkBox } from "./TalkBox";
import "./lessons.css";

export function RememberCard({ epId, draft, onPauseMain }: { epId: string; draft: RememberDraft; onPauseMain: () => void }) {
  const [d, setD] = useState(draft);
  const [talk, setTalk] = useState(false);
  const [busy, setBusy] = useState<"confirm" | "drop" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [revised, setRevised] = useState(false);

  const decide = async (action: "confirm" | "drop") => {
    setBusy(action);
    setErr(null);
    try {
      setD(await lessonsApi.decideDraft(epId, d.id, action));
      setTalk(false);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className={`remember-card is-${d.state}`} data-testid="remember-card">
      {d.understood && <p className="remember-understood">{d.understood}</p>}
      {d.fallback && (
        <p className="small warn">
          {d.error
            ? revised
              ? t("这次没能改写（{message}），按你写的原样用作这条规则的说法。", { message: d.error })
              : t("这次没能改写（{message}）。下面先放你的原话，可以点「改一下」写成你想要的说法，或者稍后再试。", { message: d.error })
            : revised
              ? t("现在没接上 AI，按你写的原样用作这条规则的说法。")
              : t("现在没接上 AI，没法帮你改写。下面先放你的原话，可以点「改一下」写成你想要的说法。")}
        </p>
      )}
      <div className="remember-label small muted">{revised ? t("改过的规则") : t("我理解的规则")}</div>
      <blockquote className="remember-rule" data-testid="remember-rule">
        {d.title}
      </blockquote>
      {d.same_as_title && (
        <p className="small muted">{t("和已有的规则「{title}」是一回事，记住后会更新那一条。", { title: d.same_as_title })}</p>
      )}
      {d.state === "pending" && (
        <>
          {!talk && (
            <>
              <p className="remember-ask">{t("是否记住这条？记住后从下一期的 AI 初剪开始照做。")}</p>
              <div className="row gap8 wrap">
                <button type="button" className="btn btn-primary" disabled={!!busy} onClick={() => decide("confirm")}>
                  <BusyLabel busy={busy === "confirm"} label={t("记住这条")} />
                </button>
                <button type="button" className="btn btn-outline" disabled={!!busy} onClick={() => setTalk(true)}>
                  {t("改一下")}
                </button>
                <button type="button" className="btn btn-outline" disabled={!!busy} onClick={() => decide("drop")}>
                  <BusyLabel busy={busy === "drop"} label={t("不用")} />
                </button>
              </div>
            </>
          )}
          {talk && (
            <TalkBox
              label={t("告诉 LACUNA 这条规则要怎么改")}
              placeholder={t("比如：只针对 Pei / 片头片尾除外 / 直接写你想要的说法")}
              onMic={onPauseMain}
              onCancel={() => setTalk(false)}
              onSend={async (text) => {
                setD(await lessonsApi.reviseDraft(epId, d.id, text));
                setRevised(true);
                setTalk(false);
              }}
            />
          )}
        </>
      )}
      {d.state === "confirmed" && (
        <p className="pstate ok" role="status">
          {t("✓ 记住了，已生效：从下一期的 AI 初剪开始照做。")}{" "}
          <a href="#/learning">{t("想撤回去「学到的规则」")}</a>
        </p>
      )}
      {d.state === "dropped" && <p className="pstate muted">{t("好的，这条不记。")}</p>}
      {err && <p className="small error">{err}</p>}
    </div>
  );
}
