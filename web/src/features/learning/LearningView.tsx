import { useEffect, useMemo, useState } from "react";
import type { Action, LearnedRule, LearningOverview } from "./api";
import { fmt } from "../../api";
import { learningApi } from "./api";
import { joinList, lang, t } from "../../i18n";
import { PageLoading } from "../loading/Loading";
import { Pager, PAGE_SIZE } from "./Pager";

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

/** A learning source as Leon reads it: a deleted episode's evidence is filed as "EP003@2026-10-21-a1b2". */
export function sourceLabel(e: string): string {
  const ep = e.replace(/\.hand_edit$/, "");
  const gone = /@\d{4}-\d{2}-\d{2}-[0-9a-f]{4}$/;
  const name = gone.test(ep) ? t("{ep}（已删）", { ep: ep.replace(gone, "") }) : ep;
  return e.endsWith(".hand_edit") ? t("{ep}（你手剪的成品）", { ep: name }) : name;
}

const STATE_LABEL: Record<string, string> = { candidate: t("待你确认"), approved: t("已生效"), rejected: t("已不采用") };

function effect(r: LearnedRule): string {
  const parts: string[] = [];
  if (r.prompt) parts.push(t("下一集 AI 第一刀会照这条剪"));
  if (r.policy?.review === true) parts.push(t("这类改动以后进审阅列表"));
  if (r.policy?.review === false) parts.push(t("这类改动以后直接应用、不用逐条过目"));
  if (r.policy?.confidence) parts.push(t("把握度低于 {confidence} 的进审阅", { confidence: r.policy.confidence }));
  return parts.join(lang === "en" ? "; " : "；");
}

/** The three groups of the page. A rule with new evidence waits for a decision but is still in force. */
type Group = "pending" | "approved" | "rejected";
const GROUPS: Group[] = ["pending", "approved", "rejected"];
const GROUP_LABEL: Record<Group, string> = { pending: t("待你决定"), approved: t("已生效"), rejected: t("已不采用") };

const inGroup = (r: LearnedRule, g: Group) =>
  g === "pending" ? r.state === "candidate" || r.updated : r.state === g;

const EMPTY: Record<Group, string> = {
  pending: t("没有等你决定的规则。你审阅、导出一集或在 AI 制作人里点「记住」之后，新的候选规则会出现在这里。"),
  approved: t("还没有采用过规则。"),
  rejected: t("没有不采用的规则。"),
};

const DONE: Record<Action, (title: string) => string> = {
  approve: (title) => t("已采用「{title}」，在「已生效」里能找到。", { title }),
  reject: (title) => t("「{title}」已移到「已不采用」。", { title }),
  reset: (title) => t("「{title}」回到了「待你决定」。", { title }),
  delete: (title) => t("已删除「{title}」，以后不会再出现。", { title }),
};
const DONE_GROUP: Record<Action, Group | null> = { approve: "approved", reject: "rejected", reset: "pending", delete: null };

export function LearningView() {
  const [ov, setOv] = useState<LearningOverview | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  // #/learning/approved (设置 → 剪辑习惯 links there) opens that tab
  const [group, setGroup] = useState<Group>(() => {
    const g = /^#\/learning\/(\w+)/.exec(window.location.hash)?.[1] as Group | undefined;
    return g && GROUPS.includes(g) ? g : "pending";
  });
  const [page, setPage] = useState(0);
  const [done, setDone] = useState<{ text: string; group: Group | null } | null>(null);

  useEffect(() => {
    learningApi.learning().then(setOv).catch((e) => setErr(String(e.message ?? e)));
  }, []);

  const lists = useMemo(() => {
    const out = { pending: [], approved: [], rejected: [] } as Record<Group, LearnedRule[]>;
    for (const r of ov?.rules ?? []) for (const g of GROUPS) if (inGroup(r, g)) out[g].push(r);
    return out;
  }, [ov]);

  const list = lists[group];
  const pages = Math.max(1, Math.ceil(list.length / PAGE_SIZE));
  const cur = Math.min(page, pages - 1); // a decision can empty the last page
  const shown = list.slice(cur * PAGE_SIZE, (cur + 1) * PAGE_SIZE);

  const pick = (g: Group) => {
    setGroup(g);
    setPage(0);
    setDone(null);
  };

  const decide = async (r: LearnedRule, action: Action) => {
    setBusy(r.id);
    try {
      setOv(await learningApi.decideRule(r.id, action));
      setPage(cur);
      const to = DONE_GROUP[action];
      // the card left this group: say where it went
      const stays = to !== null && inGroup({ ...r, state: to === "pending" ? "candidate" : to, updated: false }, group);
      setDone(stays ? null : { text: DONE[action](r.title), group: to });
    } catch (e) {
      setErr(String((e as Error).message ?? e));
    } finally {
      setBusy(null);
    }
  };

  if (err) return <p className="error pad">{t("学习页打不开：")}{err}</p>;
  if (!ov) return <PageLoading label={t("正在从你的审阅记录里学习…")} shape="list" />;
  const s = ov.stats;
  return (
    <main className="learning">
      <h1>{t("学到的规则")}</h1>
      <p className="muted">
        {t("来源：{sources}。", {
          sources: s.episodes.length ? joinList(s.episodes.map(sourceLabel)) : t("还没有"),
        })}{" "}
        {t("审阅里逐条决定 {considered} 个；所有来源合计保留 {kept}、恢复或没删 {restored}、补删 {added}。", { considered: s.considered, kept: s.kept, restored: s.restored, added: s.added })}
      </p>
      <details className="small muted learning-how">
        <summary>{t("规则是怎么来的")}</summary>
        <p>{t("规则是从你的决定和你在 AI 制作人里说的话推断的（每次导出后总结一次对话；在 AI 制作人里写好一句点「记住」会马上记一条），只有你点「采用」之后才会影响下一集。随时可以撤回。")}</p>
      </details>
      {/* tabs stay up even when every rule is gone, so a just-shown notice still has a place */}
      <>
          <div className="learning-tabs" role="tablist" aria-label={t("按状态筛选")}>
            {GROUPS.map((g) => (
              <button key={g} type="button" role="tab" aria-selected={group === g} className={group === g ? "on" : ""} onClick={() => pick(g)}>
                {GROUP_LABEL[g]}
                <span className="count">{lists[g].length}</span>
              </button>
            ))}
          </div>
          {done && (
            <p className="learning-done small" role="status">
              {done.text}{" "}
              {done.group && (
                <button type="button" className="linkish" onClick={() => pick(done.group!)}>
                  {t("去看看")}
                </button>
              )}
            </p>
          )}
          {list.length === 0 ? (
            <p className="card muted" data-testid="rules-empty">
              {ov.rules.length === 0
                ? t("还没有足够的证据形成规则。多逐条审几处（保留 / 恢复），或者在聊天里让 AI 补删，这里就会出现。也可以在 AI 制作人里写一句长期要求，点「记住」直接记一条。")
                : EMPTY[group]}
            </p>
          ) : (
            <ul className="rules" aria-label={GROUP_LABEL[group]}>
              {shown.map((r) => (
                <RuleCard key={r.id} r={r} busy={busy === r.id} decide={decide} />
              ))}
            </ul>
          )}
          <Pager page={cur} total={list.length} onPage={(p) => { setPage(p); window.scrollTo({ top: 0 }); }} />
      </>
    </main>
  );
}

function RuleCard({ r, busy, decide }: { r: LearnedRule; busy: boolean; decide: (r: LearnedRule, a: Action) => void }) {
  const [confirm, setConfirm] = useState(false);
  return (
    <li className={`card rule rule-${r.state}`} data-testid="rule">
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
                    ? t("你在 {ep} 的对话里说的（{reason}）", { ep: sourceLabel(x.episode), reason: x.reason })
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
          <button type="button" className="btn btn-primary" disabled={busy} onClick={() => decide(r, "approve")}>
            {r.updated ? t("采用新版本") : t("采用")}
          </button>
        )}
        {r.state !== "rejected" && (
          <button type="button" className="btn btn-outline" disabled={busy} onClick={() => decide(r, "reject")}>
            {r.state === "approved" ? t("撤回") : t("不采用")}
          </button>
        )}
        {r.state === "rejected" && !confirm && (
          <>
            <button type="button" className="btn btn-outline" disabled={busy} onClick={() => decide(r, "reset")}>
              {t("重新考虑")}
            </button>
            <button type="button" className="btn btn-outline rule-delete" disabled={busy} onClick={() => setConfirm(true)}>
              {t("删除")}
            </button>
          </>
        )}
        {r.state === "rejected" && confirm && (
          <span className="row gap8 wrap rule-confirm" role="group" aria-label={t("确认删除")}>
            <span className="small">{t("删除后这条规则再也不会出现，确定吗？")}</span>
            <button type="button" className="btn btn-danger" disabled={busy} onClick={() => decide(r, "delete")}>
              {t("确定删除")}
            </button>
            <button type="button" className="btn btn-outline" disabled={busy} onClick={() => setConfirm(false)}>
              {t("取消")}
            </button>
          </span>
        )}
      </div>
    </li>
  );
}
