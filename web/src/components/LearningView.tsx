import { useEffect, useState } from "react";
import type { LearnedRule, LearningOverview } from "../api";
import { api, fmt } from "../api";

const KIND_LABEL: Record<string, string> = {
  protect: "少删",
  review: "改为过目",
  trust: "不用过目",
  timid: "该直接删",
  missed: "漏删",
  taste: "品味例子",
  threshold: "把握度",
};

const STATE_LABEL: Record<string, string> = { candidate: "待你确认", approved: "已生效", rejected: "不采用" };

function effect(r: LearnedRule): string {
  const parts: string[] = [];
  if (r.prompt) parts.push("下一集 AI 第一刀会照这条剪");
  if (r.policy?.review === true) parts.push("这类改动以后进审阅列表");
  if (r.policy?.review === false) parts.push("这类改动以后直接应用、不用逐条过目");
  if (r.policy?.confidence) parts.push(`把握度低于 ${r.policy.confidence} 的进审阅`);
  return parts.join("；");
}

export function LearningView() {
  const [ov, setOv] = useState<LearningOverview | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    api.learning().then(setOv).catch((e) => setErr(String(e.message ?? e)));
  }, []);

  const decide = async (r: LearnedRule, action: "approve" | "reject" | "reset") => {
    setBusy(r.id);
    try {
      setOv(await api.decideRule(r.id, action));
    } catch (e) {
      setErr(String((e as Error).message ?? e));
    } finally {
      setBusy(null);
    }
  };

  if (err) return <p className="error pad">学习页打不开：{err}</p>;
  if (!ov) return <p className="pad muted">正在从你的审阅记录里学习…</p>;
  const s = ov.stats;
  return (
    <main className="learning">
      <h1>学到的规则</h1>
      <p className="muted">
        来源：{s.episodes.length ? s.episodes.map((e) => (e.endsWith(".hand_edit") ? `${e.replace(".hand_edit", "")}（你手剪的成品）` : e)).join("、") : "还没有"}。
        审阅里逐条决定 {s.considered} 个；所有来源合计保留 {s.kept}、恢复或没删 {s.restored}、补删 {s.added}。
      </p>
      <p className="muted small">规则是从你的决定里推断的，只有你点「采用」之后才会影响下一集。随时可以撤回。</p>
      {ov.rules.length === 0 && (
        <p className="card">还没有足够的证据形成规则。多逐条审几处（保留 / 恢复），或者在聊天里让 AI 补删，这里就会出现。</p>
      )}
      <ul className="rules" aria-label="学到的规则">
        {ov.rules.map((r) => (
          <li key={r.id} className={`card rule rule-${r.state}`} data-testid="rule">
            <div className="card-head">
              <strong>{r.title}</strong>
              <span className="row gap8">
                <span className="rtag small">{KIND_LABEL[r.kind] ?? r.kind}</span>
                <span className="chip">{r.updated ? "有新证据，待你重新确认" : STATE_LABEL[r.state] ?? r.state}</span>
              </span>
            </div>
            <p className="prose">{r.detail}</p>
            {effect(r) && <p className="small muted">采用后：{effect(r)}。</p>}
            {r.stale && <p className="small warn">新的审阅记录里已经看不出这个规律了，但它仍按你当初采用的样子生效。</p>}
            {r.examples.length > 0 && (
              <details>
                <summary className="small">看例子（{r.examples.length}）</summary>
                <ul className="small examples">
                  {r.examples.map((x, i) => (
                    <li key={i}>
                      {x.raw && <span className="mono muted">原始 {fmt(x.raw[0])} </span>}
                      「{x.text || "（停顿）"}」
                      <span className="muted">
                        {" "}
                        {x.verdict === "restored" || x.verdict === "declined" ? "你留下了" : "你删了"}
                        {x.episode.endsWith(".hand_edit") ? "（手剪成品）" : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              </details>
            )}
            <div className="row gap8 wrap">
              {(r.state !== "approved" || r.updated) && (
                <button type="button" className="btn btn-primary" disabled={busy === r.id} onClick={() => decide(r, "approve")}>
                  {r.updated ? "采用新版本" : "采用"}
                </button>
              )}
              {r.state !== "rejected" && (
                <button type="button" className="btn btn-outline" disabled={busy === r.id} onClick={() => decide(r, "reject")}>
                  {r.state === "approved" ? "撤回" : "不采用"}
                </button>
              )}
              {r.state === "rejected" && (
                <button type="button" className="btn btn-outline" disabled={busy === r.id} onClick={() => decide(r, "reset")}>
                  重新考虑
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </main>
  );
}
