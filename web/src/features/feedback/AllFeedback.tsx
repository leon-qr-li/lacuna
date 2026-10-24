import { useEffect, useState } from "react";
import { req } from "../../api";
import { locale, t } from "../../i18n";
import { BusyLabel } from "../loading/Loading";
import type { Context, Status } from "./api";
import { KIND_LABEL, STATUS_LABEL } from "./MyFeedback";

// 全部反馈（临时）: the site owner's plain list until the admin back office exists (decision
// 2026-10-24-user-feedback). Not designed on purpose; it goes when the admin batch lands.

interface Item {
  id: string;
  created: number;
  email: string;
  name: string | null;
  kind: "bug" | "idea" | "praise" | "rate" | "pmf";
  status: Status;
  text: string;
  source: string | null;
  shot: boolean;
  show: { id: string; name: string } | null;
  context: Context & { browser?: string };
  importance: string | null;
  quote_ok: boolean | null;
  platforms: string[];
  replies: { text: string; at: number }[];
  adopted: boolean;
  stars: number | null;
  saved: string | null;
  choice: string | null;
  version: string | null;
  profile: Record<string, string> | null;
}

const KIND: Record<Item["kind"], string> = { ...KIND_LABEL, rate: t("评分"), pmf: t("如果明天用不了") };
const when = (s: number) => new Date(s * 1000).toLocaleString(locale, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

export function AllFeedback() {
  const [items, setItems] = useState<Item[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = () => req<{ items: Item[] }>("GET", "/api/feedback/all").then((r) => setItems(r.items), (e) => setErr((e as Error).message));
  useEffect(() => void load(), []);
  if (err) return <p className="error">{err}</p>;
  if (!items) return <p className="muted small">{t("正在读取…")}</p>;
  return (
    <div className="fb-all" data-testid="feedback-all">
      <p className="small muted">{t("临时页面，只有站长能看。后台做好后换成后台里的反馈页。")}</p>
      <ResetPrompts />
      {items.length === 0 && <p className="muted">{t("还没有反馈。")}</p>}
      {items.map((it) => (
        <Row key={it.id} it={it} reload={load} />
      ))}
    </div>
  );
}

function Row({ it, reload }: { it: Item; reload: () => void }) {
  const [text, setText] = useState("");
  const [status, setStatus] = useState<Status>(it.status);
  const [adopted, setAdopted] = useState(it.adopted);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const answer = it.kind === "rate" || it.kind === "pmf";
  const send = async () => {
    setBusy(true);
    setNote(null);
    try {
      const r = await req<{ mailed: boolean }>("POST", `/api/feedback/${it.id}/reply`, { text: text.trim() || null, status, adopted });
      setText("");
      setNote(r.mailed ? t("已保存，已发邮件给对方") : t("已保存"));
      reload();
    } catch (e) {
      setNote((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const c = it.context;
  return (
    <article className="fb-item" data-testid="feedback-all-item">
      <div className="fb-item-head">
        <span className="chip chip-plain">{KIND[it.kind]}</span>
        <b className="fb-item-text fb-wrap">{it.text || "—"}</b>
        {!answer && <span className="chip">{STATUS_LABEL[it.status]}</span>}
      </div>
      <div className="small muted">
        {[when(it.created), it.name ? `${it.name} · ${it.email}` : it.email, it.show?.name, it.version].filter(Boolean).join(" · ")}
      </div>
      <dl className="fb-dl small">
        {it.stars != null && <><dt>{t("评分")}</dt><dd>{"★".repeat(it.stars)}{it.saved ? ` · ${it.saved}` : ""}</dd></>}
        {it.choice && <><dt>{t("回答")}</dt><dd>{it.choice}</dd></>}
        {it.importance && <><dt>{t("重要程度")}</dt><dd>{it.importance}</dd></>}
        {it.quote_ok != null && <><dt>{t("可公开引用")}</dt><dd>{it.quote_ok ? t("是") : t("否")}</dd></>}
        {it.platforms.length > 0 && <><dt>{t("平台")}</dt><dd>{it.platforms.join(" / ")}</dd></>}
        {it.source && it.source !== "button" && <><dt>{t("从哪来")}</dt><dd>{it.source}</dd></>}
        {c.page && <><dt>{t("页面")}</dt><dd>{[c.title, c.page, c.at != null ? `${c.at}s` : null].filter(Boolean).join(" · ")}</dd></>}
        {c.error && <><dt>{t("报错")}</dt><dd>{c.error}{c.error_code ? ` (${c.error_code})` : ""}</dd></>}
        {(c.browser || c.lang) && <><dt>{t("环境")}</dt><dd>{[c.browser, c.lang].filter(Boolean).join(" · ")}</dd></>}
        {it.profile && <><dt>{t("节目画像")}</dt><dd>{Object.entries(it.profile).map(([k, v]) => `${k}: ${v}`).join(" · ")}</dd></>}
      </dl>
      {c.actions && c.actions.length > 0 && (
        <details className="small">
          <summary>{t("最近 {n} 步操作", { n: c.actions.length })}</summary>
          <pre className="fb-steps">{c.actions.join("\n")}</pre>
        </details>
      )}
      {it.shot && (
        <a href={`/api/feedback/${it.id}/shot`} target="_blank" rel="noreferrer" className="fb-all-shot">
          <img src={`/api/feedback/${it.id}/shot`} alt={t("截图")} loading="lazy" />
        </a>
      )}
      {it.replies.map((r, i) => (
        <div key={i} className="fb-reply">
          <span className="small fb-reply-who">{t("你的回复")} · {when(r.at)}</span>
          <p>{r.text}</p>
        </div>
      ))}
      {!answer && (
        <div className="fb-all-reply">
          <textarea className="fb-text" rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder={t("回复对方（可以不写，只改状态）")} data-testid="feedback-all-text" />
          <div className="row gap8 wrap">
            <select value={status} onChange={(e) => setStatus(e.target.value as Status)} aria-label={t("状态")} data-testid="feedback-all-status">
              {(Object.keys(STATUS_LABEL) as Status[]).map((s) => (
                <option key={s} value={s}>
                  {STATUS_LABEL[s]}
                </option>
              ))}
            </select>
            <label className="fb-check">
              <input type="checkbox" checked={adopted} onChange={(e) => setAdopted(e.target.checked)} data-testid="feedback-all-adopted" />
              <span className="small">{t("采纳（本月送 1 小时）")}</span>
            </label>
            <span className="grow" />
            <button type="button" className="btn btn-primary btn-small" disabled={busy} onClick={send} data-testid="feedback-all-send">
              <BusyLabel busy={busy} label={t("保存并通知")} />
            </button>
          </div>
          {note && <p className="small muted">{note}</p>}
        </div>
      )}
    </article>
  );
}

/** 验收: ask an account the one-question prompts again, as if it was never asked. */
function ResetPrompts() {
  const [email, setEmail] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const reset = async () => {
    setNote(null);
    try {
      const r = await req<{ exported: number }>("POST", "/api/feedback/prompt/reset", { email: email.trim() });
      setNote(t("已重置：下次导出完成时会再问。这个账号导出过 {n} 集。", { n: r.exported }));
    } catch (e) {
      setNote((e as Error).message);
    }
  };
  return (
    <form
      className="row gap8 wrap fb-reset"
      onSubmit={(e) => {
        e.preventDefault();
        if (email.trim()) void reset();
      }}
    >
      <span className="small">{t("测试用：让某个账号重新被问「一题」")}</span>
      <input className="fb-text fb-reset-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder={t("账号邮箱")} aria-label={t("账号邮箱")} data-testid="feedback-reset-email" />
      <button type="submit" className="btn btn-outline btn-small" disabled={!email.trim()} data-testid="feedback-reset">
        {t("重置")}
      </button>
      {note && <span className="small muted">{note}</span>}
    </form>
  );
}
