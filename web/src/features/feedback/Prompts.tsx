import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { t } from "../../i18n";
import { BusyLabel } from "../loading/Loading";
import { feedbackApi, type PromptKind } from "./api";
import { isSignedIn } from "./unread";

const SAVED: { id: string; label: string }[] = [
  { id: "none", label: t("没省") },
  { id: "half", label: t("半小时内") },
  { id: "1-2h", label: t("1–2 小时") },
  { id: "2h+", label: t("2 小时以上") },
  { id: "never", label: t("以前不剪") },
];
const PMF: { id: string; label: string }[] = [
  { id: "very", label: t("非常失望") },
  { id: "somewhat", label: t("有点失望") },
  { id: "not", label: t("无所谓，我有别的办法") },
];

/**
 * 关键时刻只问一题 (design A5, A6): after an export finished, the server says whether to ask now
 * (评分 after the first episode, 「如果明天用不了」 after the third; at most once a week, never after
 * 不再问我). One card in the corner; editing goes on underneath.
 */
let asking = false;
export async function askAfterExport() {
  if (asking || !isSignedIn()) return;
  let ask: PromptKind | null = null;
  try {
    ask = (await feedbackApi.due()).ask;
  } catch {
    return;
  }
  if (!ask) return;
  asking = true;
  const host = document.createElement("div");
  host.className = "fb-prompt-host";
  document.body.appendChild(host);
  const root = createRoot(host);
  const close = () => {
    root.unmount();
    host.remove();
    asking = false;
  };
  root.render(<PromptCard kind={ask} close={close} />);
}

export function PromptCard({ kind, close }: { kind: PromptKind; close: () => void }) {
  const [stars, setStars] = useState(0);
  const [hover, setHover] = useState(0);
  const [saved, setSaved] = useState<string | null>(null);
  const [choice, setChoice] = useState<string | null>(null);
  const [score, setScore] = useState<number | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [thanks, setThanks] = useState(false);
  useEffect(() => {
    if (!thanks) return;
    const id = window.setTimeout(close, 1800);
    return () => window.clearTimeout(id);
  }, [thanks, close]);

  const out = async (outcome: "later" | "never") => {
    try {
      await feedbackApi.answer(kind, outcome);
    } catch {
      /* asked again later at worst */
    }
    close();
  };
  const send = async () => {
    setBusy(true);
    setErr(null);
    try {
      await feedbackApi.answer(kind, "sent", kind === "rate" ? { stars, saved, text } : kind === "nps" ? { score, text } : { choice, text });
      setThanks(true);
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  };
  const ready = kind === "rate" ? stars > 0 : kind === "nps" ? score !== null : !!choice;

  return (
    <section className="fb-prompt" role="dialog" aria-labelledby="fb-prompt-title" data-testid={`feedback-prompt-${kind}`}>
      {thanks ? (
        <p className="fb-prompt-thanks">{t("谢谢你，我们都会看。")}</p>
      ) : (
        <>
          {kind === "rate" ? (
            <>
              <span className="small muted">{t("只问一个问题")}</span>
              <h3 id="fb-prompt-title">{t("这集剪得怎么样？")}</h3>
              <div className="fb-stars" role="radiogroup" aria-label={t("评分")} onMouseLeave={() => setHover(0)}>
                {[1, 2, 3, 4, 5].map((n) => (
                  <button
                    key={n}
                    type="button"
                    role="radio"
                    aria-checked={stars === n}
                    aria-label={t("{n} 星", { n })}
                    className={(hover || stars) >= n ? "on" : ""}
                    onMouseEnter={() => setHover(n)}
                    onClick={() => setStars(n)}
                    data-testid={`feedback-star-${n}`}
                  >
                    ★
                  </button>
                ))}
              </div>
              <span className="fb-label">{t("比你以前自己剪，省了多少时间？")}</span>
              <div className="fb-kinds">
                {SAVED.map((x) => (
                  <button key={x.id} type="button" className={`fb-chip small${saved === x.id ? " on" : ""}`} aria-pressed={saved === x.id} onClick={() => setSaved(x.id)}>
                    {x.label}
                  </button>
                ))}
              </div>
              <label className="fb-label" htmlFor="fb-prompt-text">
                {stars > 0 && stars < 5 ? t("还差在哪？（可以不写）") : t("想说点什么？（可以不写）")}
              </label>
            </>
          ) : kind === "nps" ? (
            <>
              <span className="small muted">{t("只问一个问题")}</span>
              <h3 id="fb-prompt-title">{t("你有多大可能把 LACUNA 推荐给做播客的朋友？")}</h3>
              <div className="fb-nps" role="radiogroup" aria-label={t("0 到 10 分")}>
                {Array.from({ length: 11 }, (_, n) => (
                  <button key={n} type="button" role="radio" aria-checked={score === n} className={score === n ? "on" : ""} onClick={() => setScore(n)} data-testid={`feedback-nps-${n}`}>
                    {n}
                  </button>
                ))}
              </div>
              <div className="fb-nps-ends small muted">
                <span>{t("完全不会")}</span>
                <span>{t("一定会")}</span>
              </div>
              <label className="fb-label" htmlFor="fb-prompt-text">
                {t("为什么打这个分？（可以不写）")}
              </label>
            </>
          ) : (
            <>
              <span className="small muted">{t("你已经用 LACUNA 剪了 3 集 · 只问一个问题")}</span>
              <h3 id="fb-prompt-title">{t("如果从明天起用不了 LACUNA，你会……")}</h3>
              <div className="fb-choices" role="radiogroup">
                {PMF.map((x) => (
                  <button key={x.id} type="button" role="radio" aria-checked={choice === x.id} className={`fb-choice${choice === x.id ? " on" : ""}`} onClick={() => setChoice(x.id)} data-testid={`feedback-pmf-${x.id}`}>
                    {x.label}
                  </button>
                ))}
              </div>
              <label className="fb-label" htmlFor="fb-prompt-text">
                {t("LACUNA 对你最大的用处是什么？（可以不写）")}
              </label>
            </>
          )}
          <textarea id="fb-prompt-text" className="fb-text" rows={2} maxLength={2000} value={text} onChange={(e) => setText(e.target.value)} />
          {err && <p className="error small">{err}</p>}
          <div className="fb-prompt-foot">
            <button type="button" className="btn btn-ghost btn-small" onClick={() => out("never")} data-testid="feedback-prompt-never">
              {t("不再问我")}
            </button>
            <span className="grow" />
            <button type="button" className="btn btn-outline btn-small" onClick={() => out("later")} data-testid="feedback-prompt-later">
              {t("以后再说")}
            </button>
            <button type="button" className="btn btn-primary btn-small" disabled={!ready || busy} onClick={send} data-testid="feedback-prompt-send">
              <BusyLabel busy={busy} label={t("发送")} />
            </button>
          </div>
        </>
      )}
    </section>
  );
}
