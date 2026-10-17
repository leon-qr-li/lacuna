import { useEffect, useState } from "react";
import type { LearnedRule, LearningOverview } from "./api";
import { fmt } from "../../api";
import { learningApi } from "./api";
import { joinList, lang, t } from "../../i18n";

const KIND_LABEL: Record<string, string> = {
  protect: t("少删"),
  review: t("改为过目"),
  trust: t("不用过目"),
  timid: t("该直接删"),
  missed: t("漏删"),
  taste: t("品味例子"),
  threshold: t("把握度"),
  ask: t("你说过的"),
};

const STATE_LABEL: Record<string, string> = { candidate: t("待你确认"), approved: t("已生效"), rejected: t("不采用") };

function effect(r: LearnedRule): string {
  const parts: string[] = [];
  if (r.prompt) parts.push(t("下一集 AI 第一刀会照这条剪"));
  if (r.policy?.review === true) parts.push(t("这类改动以后进审阅列表"));
  if (r.policy?.review === false) parts.push(t("这类改动以后直接应用、不用逐条过目"));
  if (r.policy?.confidence) parts.push(t("把握度低于 {confidence} 的进审阅", { confidence: r.policy.confidence }));
  return parts.join(lang === "en" ? "; " : "；");
}

export function LearningView() {
  const [ov, setOv] = useState<LearningOverview | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    learningApi.learning().then(setOv).catch((e) => setErr(String(e.message ?? e)));
  }, []);

  const decide = async (r: LearnedRule, action: "approve" | "reject" | "reset") => {
    setBusy(r.id);
    try {
      setOv(await learningApi.decideRule(r.id, action));
    } catch (e) {
      setErr(String((e as Error).message ?? e));
    } finally {
      setBusy(null);
    }
  };

  if (err) return <p className="error pad">{t("学习页打不开：")}{err}</p>;
  if (!ov) return <p className="pad muted">{t("正在从你的审阅记录里学习…")}</p>;
  const s = ov.stats;
  return (
    <main className="learning">
      <h1>{t("学到的规则")}</h1>
      <p className="muted">
        {t("来源：{sources}。", {
          sources: s.episodes.length ? joinList(s.episodes.map((e) => (e.endsWith(".hand_edit") ? t("{ep}（你手剪的成品）", { ep: e.replace(".hand_edit", "") }) : e))) : t("还没有"),
        })}{" "}
        {t("审阅里逐条决定 {considered} 个；所有来源合计保留 {kept}、恢复或没删 {restored}、补删 {added}。", { considered: s.considered, kept: s.kept, restored: s.restored, added: s.added })}
      </p>
      <p className="muted small">
        {t("规则是从你的决定和你在 AI 制作人里说的话推断的（每次导出后总结一次对话；说「记住：……」会马上记一条），只有你点「采用」之后才会影响下一集。随时可以撤回。")}
      </p>
      {ov.rules.length === 0 && (
        <p className="card">{t("还没有足够的证据形成规则。多逐条审几处（保留 / 恢复），或者在聊天里让 AI 补删，这里就会出现。也可以在 AI 制作人里说「记住：……」，直接记一条。")}</p>
      )}
      <ul className="rules" aria-label={t("学到的规则")}>
        {ov.rules.map((r) => (
          <li key={r.id} className={`card rule rule-${r.state}`} data-testid="rule">
            <div className="card-head">
              <strong>{r.title}</strong>
              <span className="row gap8">
                <span className="rtag small">{KIND_LABEL[r.kind] ?? r.kind}</span>
                <span className="chip">{r.updated ? t("有新证据，待你重新确认") : STATE_LABEL[r.state] ?? r.state}</span>
              </span>
            </div>
            <p className="prose">{r.detail}</p>
            {effect(r) && <p className="small muted">{t("采用后：{effect}。", { effect: effect(r) })}</p>}
            {r.stale && <p className="small warn">{t("新的审阅记录里已经看不出这个规律了，但它仍按你当初采用的样子生效。")}</p>}
            {r.examples.length > 0 && (
              <details>
                <summary className="small">{t("看例子（{n}）", { n: r.examples.length })}</summary>
                <ul className="small examples">
                  {r.examples.map((x, i) => (
                    <li key={i}>
                      {x.raw && <span className="mono muted">{t("原始")} {fmt(x.raw[0])} </span>}
                      「{x.text || t("（停顿）")}」
                      <span className="muted">
                        {" "}
                        {x.verdict === "said"
                          ? t("你在 {ep} 的对话里说的（{reason}）", { ep: x.episode, reason: x.reason })
                          : x.verdict === "restored" || x.verdict === "declined" ? t("你留下了") : t("你删了")}
                        {x.episode.endsWith(".hand_edit") ? t("（手剪成品）") : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              </details>
            )}
            <div className="row gap8 wrap">
              {(r.state !== "approved" || r.updated) && (
                <button type="button" className="btn btn-primary" disabled={busy === r.id} onClick={() => decide(r, "approve")}>
                  {r.updated ? t("采用新版本") : t("采用")}
                </button>
              )}
              {r.state !== "rejected" && (
                <button type="button" className="btn btn-outline" disabled={busy === r.id} onClick={() => decide(r, "reject")}>
                  {r.state === "approved" ? t("撤回") : t("不采用")}
                </button>
              )}
              {r.state === "rejected" && (
                <button type="button" className="btn btn-outline" disabled={busy === r.id} onClick={() => decide(r, "reset")}>
                  {t("重新考虑")}
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </main>
  );
}
