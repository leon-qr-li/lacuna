// 反馈 (decision: 收件箱 two panes): the list on the left, the item on the right with its page, steps and screenshot,
// status, 采纳 (+1 hour), tags, internal notes, and the reply (shown in the person's 我的反馈 and emailed).
// Tabs: 「一题」 answers, 用户画像 (a new show's questions), 推荐意愿 (NPS). User text is shown as text only.
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { PageProps } from "../Shell";
import { t } from "../i18n";
import { EDITING, FB_KIND, FB_STATUS, PMF, REGION, SAVED, planName } from "../labels";
import type { FbItem, FbStatus, FeedbackData, Note, Prompts, Template } from "../types";
import { demoData } from "../demo";
import { Avatar, Card, Chips, Empty, HBar, Icon, Loading, PageHead, Pill, Tabs, ago, act, dialog, fmtDate, fmtTime, isDemo, toast, useData } from "../ui";

type Tab = "inbox" | "oneq" | "profile" | "nps";
type Filter = "open" | "all" | "bug" | "idea" | "praise" | "publish" | "adopted";

export function FeedbackPage(_: PageProps) {
  const [tab, setTab] = useState<Tab>("inbox");
  const fb = useData<FeedbackData>("/api/admin/feedback");
  const pr = useData<Prompts>(tab === "inbox" ? null : "/api/admin/feedback/prompts");
  const open = fb.data ? fb.data.items.filter((f) => f.status === "received" || f.status === "working").length : null;
  return (
    <>
      <PageHead
        title={t("反馈")}
        sub={fb.data ? t("共 {n} 条 · 回复会出现在用户的「我的反馈」里，同时发邮件", { n: fb.data.items.length }) : undefined}
      />
      <Tabs<Tab>
        value={tab}
        onChange={setTab}
        items={[
          { id: "inbox", label: t("收件箱"), n: open },
          { id: "oneq", label: t("「一题」") },
          { id: "profile", label: t("用户画像") },
          { id: "nps", label: t("推荐意愿") },
        ]}
      />
      {tab === "inbox" && (fb.data ? <Inbox data={fb.data} setData={fb.set} /> : <Loading error={fb.error} />)}
      {tab !== "inbox" && (pr.data ? tab === "oneq" ? <OneQ p={pr.data} /> : tab === "profile" ? <Profiles p={pr.data} /> : <Nps p={pr.data} /> : <Loading error={pr.error} />)}
    </>
  );
}

function Inbox({ data, setData }: { data: FeedbackData; setData: (d: FeedbackData) => void }) {
  const [filter, setFilter] = useState<Filter>("open");
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<string | null>(null);
  const [mobileDetail, setMobileDetail] = useState(false);
  const list = useMemo(() => {
    const s = q.trim().toLowerCase();
    return data.items.filter((f) => {
      const keep =
        filter === "all" ||
        (filter === "open" && (f.status === "received" || f.status === "working")) ||
        (filter === "adopted" && f.adopted) ||
        (filter === "publish" && f.source === "publish") ||
        f.kind === filter;
      return keep && (!s || f.text.toLowerCase().includes(s) || f.email.includes(s) || (f.name || "").toLowerCase().includes(s) || f.tags.some((x) => x.toLowerCase().includes(s)));
    });
  }, [data.items, filter, q]);
  const item = list.find((f) => f.id === sel) ?? list[0];
  const update = (it: FbItem) => setData({ ...data, items: data.items.map((x) => (x.id === it.id ? it : x)) });
  return (
    <>
      <div className="a-filters">
        <Chips<Filter>
          value={filter}
          onChange={setFilter}
          items={[
            { id: "open", label: t("没处理完") },
            { id: "all", label: t("全部") },
            { id: "bug", label: t("问题") },
            { id: "idea", label: t("建议") },
            { id: "praise", label: t("夸一句") },
            { id: "publish", label: t("自动发布") },
            { id: "adopted", label: t("已采纳") },
          ]}
        />
        <span className="spacer" />
        <input className="a-inp" type="search" placeholder={t("搜索反馈内容、用户、标签")} value={q} onChange={(e) => setQ(e.target.value)} aria-label={t("搜索")} data-testid="fb-search" />
      </div>
      {!list.length ? (
        <Card>
          <Empty title={t("这里没有反馈")} sub={filter === "open" ? t("都处理完了。") : t("换一个筛选看看。")} />
        </Card>
      ) : (
        <div className={`a-inbox${mobileDetail ? " detail" : ""}`} data-testid="inbox">
          <div className="a-ilist" role="list">
            {list.map((f) => (
              <button
                key={f.id}
                type="button"
                role="listitem"
                className={`a-ii${f.id === item?.id ? " sel" : ""}${f.status === "received" ? " unread" : ""}`}
                onClick={() => {
                  setSel(f.id);
                  setMobileDetail(true);
                }}
                data-testid="fb-item"
              >
                <span className="l1">
                  <Avatar name={f.name || f.email} />
                  <b>{f.name || f.email}</b>
                  <Pill tone={FB_STATUS[f.status].tone}>{FB_STATUS[f.status].label()}</Pill>
                  <span className="tm">{ago(f.created)}</span>
                </span>
                <span className="tx">{f.text}</span>
                <span className="l3">
                  <Pill>{FB_KIND[f.kind]?.() ?? f.kind}</Pill>
                  {f.source === "error" && <Pill tone="bad">{t("出错时")}</Pill>}
                  {f.shot && <Pill>{t("有截图")}</Pill>}
                  {f.adopted && <Pill tone="ok">{t("已采纳")}</Pill>}
                  {f.tags.map((x) => (
                    <Pill key={x}>{x}</Pill>
                  ))}
                </span>
              </button>
            ))}
          </div>
          {item && <Detail key={item.id} item={item} templates={data.templates} knownTags={data.known_tags} update={update} back={() => setMobileDetail(false)} />}
        </div>
      )}
    </>
  );
}

function Detail({ item, templates, knownTags, update, back }: { item: FbItem; templates: Template[]; knownTags: string[]; update: (f: FbItem) => void; back: () => void }) {
  const [text, setText] = useState("");
  const [mail, setMail] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notes, setNotes] = useState<Note[] | null>(null);
  const [tagIn, setTagIn] = useState("");
  const [shotOpen, setShotOpen] = useState(false);
  useEffect(() => {
    if (item.notes === 0) return setNotes([]);
    if (isDemo()) return setNotes((demoData(`/api/admin/notes?target=fb:${item.id}`) as { notes: Note[] }).notes);
    api<{ notes: Note[] }>("GET", `/api/admin/notes?target=${encodeURIComponent(`fb:${item.id}`)}`).then(
      (r) => setNotes(r.notes),
      () => setNotes([]),
    );
  }, [item.id, item.notes]);
  const reply = async (body: { text?: string; status?: FbStatus; adopted?: boolean; mail?: boolean }, done: string) => {
    setBusy(true);
    const r = await act(() => api<{ item: FbItem; mailed: boolean }>("POST", `/api/admin/feedback/${item.id}/reply`, body), done);
    setBusy(false);
    if (r) {
      update(r.item);
      if (body.text) setText("");
    }
  };
  const setTags = async (tags: string[]) => {
    const r = await act(() => api<{ tags: string[] }>("PUT", `/api/admin/feedback/${item.id}/tags`, { tags }));
    if (r) update({ ...item, tags: r.tags });
  };
  const addNote = async () => {
    if (!text.trim()) return;
    const r = await act(() => api<{ notes: Note[] }>("POST", "/api/admin/notes", { target: `fb:${item.id}`, text }), t("备注已保存"));
    if (r) {
      setNotes(r.notes);
      setText("");
      update({ ...item, notes: r.notes.length });
    }
  };
  const ctx = item.context || {};
  return (
    <div className="a-idetail" data-testid="fb-detail">
      <button type="button" className="a-btn ghost sm a-back" onClick={back}>
        ‹ {t("返回列表")}
      </button>
      <div className="a-row wrap">
        <Avatar name={item.name || item.email} />
        <div className="a-grow a-fb-who">
          <b>{item.name || item.email}</b>
          <div className="a-muted small">
            {item.email} · {planName(item.plan)} · {t("加入于 {d}", { d: fmtDate(item.joined) })}
          </div>
        </div>
        <select
          className="a-inp"
          aria-label={t("状态")}
          value={item.status}
          onChange={(e) => reply({ status: e.target.value as FbStatus, mail: false }, t("状态已更新"))}
          data-testid="fb-status"
        >
          {(Object.keys(FB_STATUS) as FbStatus[]).map((s) => (
            <option key={s} value={s}>
              {FB_STATUS[s].label()}
            </option>
          ))}
        </select>
        <button
          type="button"
          className={`a-btn ${item.adopted ? "" : "acc"}`}
          disabled={busy}
          onClick={() => reply({ adopted: !item.adopted, mail: !item.adopted }, item.adopted ? t("已取消采纳") : t("已采纳，对方本月 +1 小时，已发邮件"))}
          data-testid="fb-adopt"
        >
          <Icon name="star" />
          {item.adopted ? t("已采纳 · +1 小时（点一下取消）") : t("采纳（本月 +1 小时）")}
        </button>
      </div>
      <div className="a-msg">
        <div className="a-row small a-muted">
          <Pill>{FB_KIND[item.kind]?.() ?? item.kind}</Pill>
          <span>{fmtTime(item.created)}</span>
          {item.importance && <Pill tone="info">{item.importance === "need" ? t("很需要") : item.importance === "nice" ? t("有了更好") : t("无所谓")}</Pill>}
          {item.quote_ok && <Pill tone="ok">{t("同意被引用")}</Pill>}
        </div>
        <div className="body" data-testid="fb-text">
          {item.text}
        </div>
        {item.platforms.length > 0 && <div className="a-muted small">{t("想发布到：{p}", { p: item.platforms.join(" · ") })}</div>}
      </div>
      <div className="a-ctx">
        {ctx.page && <Pill>{t("页面：{v}", { v: ctx.page })}</Pill>}
        {item.show && <Pill>{t("节目：{v}", { v: item.show.name })}</Pill>}
        {ctx.episode && <Pill>{t("剧集：{v}", { v: ctx.episode })}</Pill>}
        {ctx.browser && <Pill>{ctx.browser}</Pill>}
        {ctx.lang && <Pill>{ctx.lang === "en" ? t("界面英文") : t("界面中文")}</Pill>}
        {item.version && <Pill>v.{item.version.slice(0, 7)}</Pill>}
        {item.profile?.region && <Pill>{REGION[item.profile.region]?.() ?? item.profile.region}</Pill>}
      </div>
      {ctx.error && (
        <div className="a-alert bad small">
          <Icon name="shield" />
          <span>{ctx.error}</span>
        </div>
      )}
      {ctx.actions && ctx.actions.length > 0 && (
        <details className="a-steps">
          <summary>{t("出事前的 {n} 步操作", { n: ctx.actions.length })}</summary>
          <ol>
            {ctx.actions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ol>
        </details>
      )}
      {item.shot && (
        <div>
          <div className="a-lbl">{t("用户附带的截图（只按图片显示）")}</div>
          <button type="button" className="a-shot" onClick={() => setShotOpen(!shotOpen)} aria-expanded={shotOpen}>
            <img src={`/api/admin/feedback/${encodeURIComponent(item.id)}/shot`} alt={t("截图")} className={shotOpen ? "big" : ""} data-testid="fb-shot" />
          </button>
        </div>
      )}
      <div>
        <div className="a-lbl">{t("标签")}</div>
        <div className="a-row wrap">
          {item.tags.map((x) => (
            <span key={x} className="a-pill acc">
              {x}
              <button type="button" className="a-x" aria-label={t("去掉标签 {x}", { x })} onClick={() => setTags(item.tags.filter((y) => y !== x))}>
                ×
              </button>
            </span>
          ))}
          <input
            className="a-inp sm"
            list="fb-known-tags"
            placeholder={t("加标签，回车")}
            value={tagIn}
            maxLength={24}
            onChange={(e) => setTagIn(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && tagIn.trim()) {
                setTags([...item.tags, tagIn.trim()]);
                setTagIn("");
              }
            }}
            data-testid="fb-tag-input"
          />
          <datalist id="fb-known-tags">
            {knownTags.map((x) => (
              <option key={x} value={x} />
            ))}
          </datalist>
        </div>
      </div>
      {item.replies.length > 0 && (
        <div className="a-thread">
          {item.replies.map((r, i) => (
            <div key={i} className="a-bubble">
              <div className="who">
                {t("回复")} · {fmtTime(r.at)}
              </div>
              {r.text}
            </div>
          ))}
        </div>
      )}
      <div className="a-thread">
        <div className="a-lbl">{t("内部备注 · 只有站长和管理员能看到")}</div>
        {notes === null ? null : notes.length ? (
          notes.map((n) => (
            <div key={n.id} className="a-bubble note">
              <div className="who">
                {n.email} · {fmtTime(n.ts)}
              </div>
              {n.text}
            </div>
          ))
        ) : (
          <span className="a-muted small">{t("还没有备注")}</span>
        )}
      </div>
      <div className="a-reply">
        <textarea
          placeholder={t("写回复… 会出现在用户的「我的反馈」里")}
          value={text}
          maxLength={8000}
          onChange={(e) => setText(e.target.value)}
          aria-label={t("回复")}
          data-testid="fb-reply-text"
        />
        <div className="rb">
          <select
            className="a-inp sm"
            value=""
            aria-label={t("插入模板")}
            onChange={(e) => {
              const tp = templates.find((x) => x.id === e.target.value);
              if (tp) setText(tp.text);
            }}
          >
            <option value="">{t("插入模板…")}</option>
            {templates.map((x) => (
              <option key={x.id} value={x.id}>
                {x.title}
              </option>
            ))}
          </select>
          <label className="a-row small">
            <input type="checkbox" checked={mail} onChange={(e) => setMail(e.target.checked)} />
            {t("同时发邮件")}
          </label>
          <span className="spacer" />
          <button type="button" className="a-btn" disabled={!text.trim() || busy} onClick={addNote} data-testid="fb-note">
            {t("存为内部备注")}
          </button>
          <button
            type="button"
            className="a-btn pri"
            disabled={!text.trim() || busy}
            onClick={() => reply({ text, mail, status: item.status === "received" ? "working" : undefined }, mail ? t("已回复，邮件已发出") : t("已回复"))}
            data-testid="fb-reply"
          >
            {t("回复")}
          </button>
        </div>
      </div>
      <TemplatesLink templates={templates} />
    </div>
  );
}

function TemplatesLink({ templates }: { templates: Template[] }) {
  const edit = async () => {
    const title = await dialog({ title: t("新的回复模板"), ok: t("下一步"), input: { label: t("模板名字") } });
    if (!title) return;
    const text = await dialog({ title: t("新的回复模板"), ok: t("保存"), input: { label: t("模板内容"), multiline: true } });
    if (!text) return;
    const r = await act(() => api("PUT", "/api/admin/templates", { items: [...templates, { id: `t${Date.now()}`, title, text }] }), t("模板已保存，刷新后能用"));
    if (r) toast(t("模板已保存，刷新后能用"));
  };
  return (
    <button type="button" className="a-btn ghost sm" onClick={edit}>
      <Icon name="plus" /> {t("加一个回复模板")}
    </button>
  );
}

// ------------------------------------------------------------------ 「一题」, 画像, NPS
function dist(rec: Record<string, number>, names: Record<string, () => string>, order?: string[]) {
  const keys = order ?? Object.keys(rec);
  const total = Object.values(rec).reduce((a, b) => a + b, 0);
  const max = Math.max(1, ...Object.values(rec));
  if (!total) return <p className="a-muted">{t("还没有人回答")}</p>;
  return (
    <div className="a-hbars">
      {keys.map((k) => (
        <HBar key={k} label={names[k]?.() ?? k} value={rec[k] ?? 0} max={max} text={`${rec[k] ?? 0} · ${Math.round(((rec[k] ?? 0) / total) * 100)}%`} />
      ))}
    </div>
  );
}

function Quotes({ p, kind }: { p: Prompts; kind: string }) {
  const qs = p.quotes.filter((q) => q.kind === kind);
  if (!qs.length) return <p className="a-muted small">{t("还没有原话")}</p>;
  return (
    <ul className="a-quotes">
      {qs.slice(0, 20).map((q, i) => (
        <li key={i}>
          <span className="a-muted small">
            {q.name || q.email} · {ago(q.at)}
            {q.stars ? ` · ${"★".repeat(q.stars)}` : ""}
            {q.score !== undefined && q.score !== null ? ` · ${q.score}/10` : ""}
          </span>
          <span>{q.text}</span>
        </li>
      ))}
    </ul>
  );
}

function OneQ({ p }: { p: Prompts }) {
  const stars = ["5", "4", "3", "2", "1"];
  const starNames = Object.fromEntries(stars.map((s) => [s, () => "★".repeat(Number(s))]));
  const rateN = Object.values(p.rate).reduce((a, b) => a + b, 0);
  const avg = rateN ? Object.entries(p.rate).reduce((a, [k, v]) => a + Number(k) * v, 0) / rateN : null;
  return (
    <div className="a-grid g2">
      <Card title={t("这集剪得怎么样？")} sub={t("第 1 次导出后问 · {n} 人回答 · 平均 {avg}", { n: rateN, avg: avg ? avg.toFixed(1) : "—" })}>
        {dist(p.rate, starNames, stars)}
        <div className="a-sep" />
        <div className="a-lbl">{t("比以前自己剪省了多少时间")}</div>
        {dist(p.saved, SAVED, Object.keys(SAVED))}
        <div className="a-sep" />
        <Quotes p={p} kind="rate" />
      </Card>
      <Card title={t("如果从明天起用不了 LACUNA")} sub={t("第 3 次导出后问 · 「非常失望」超过 40% 说明产品有人离不开")}>
        {dist(p.pmf, PMF, Object.keys(PMF))}
        <div className="a-sep" />
        <Quotes p={p} kind="pmf" />
      </Card>
      <ResetPrompts />
    </div>
  );
}

function ResetPrompts() {
  const go = async () => {
    const email = await dialog({ title: t("重置「一题」"), body: t("让这个人下次导出后重新被问到「一题」（测试用）。"), ok: t("重置"), input: { label: t("邮箱") } });
    if (email) await act(() => api("POST", "/api/admin/feedback/prompt-reset", { email }), t("已重置"));
  };
  return (
    <Card title={t("测试「一题」")}>
      <p className="a-muted small">{t("想自己再试一次弹出的问题？把测试账号重置一下。")}</p>
      <button type="button" className="a-btn" onClick={go} data-testid="prompt-reset">
        {t("重置某个人的「一题」")}
      </button>
    </Card>
  );
}

function Profiles({ p }: { p: Prompts }) {
  const pr = p.profiles;
  return (
    <div className="a-grid g3">
      <Card title={t("在哪里")} sub={t("{n} 个节目回答", { n: pr.n })}>
        {dist(pr.region, REGION, Object.keys(REGION))}
      </Card>
      <Card title={t("以前怎么剪")}>{dist(pr.editing, EDITING, Object.keys(EDITING))}</Card>
      <Card title={t("节目语言")}>{dist(pr.lang, { zh: () => t("中文节目"), en: () => t("英文节目") }, ["zh", "en"])}</Card>
    </div>
  );
}

function Nps({ p }: { p: Prompts }) {
  const n = p.nps;
  if (!n.n)
    return (
      <Card>
        <Empty icon="star" title={t("还没有打分")} sub={t("用户导出第 3 集以后会问一次 0 到 10 分，之后每 3 个月问一次。")} />
      </Card>
    );
  const scores = Array.from({ length: 11 }, (_, i) => n.scores[String(i)] ?? 0);
  const max = Math.max(1, ...scores);
  return (
    <div className="a-grid g-12">
      <Card title={t("推荐意愿（NPS）")} sub={t("{n} 人打分", { n: n.n })}>
        <div className="a-big">{n.score ?? "—"}</div>
        <div className="a-hbars">
          <HBar label={t("推荐者 9–10")} value={n.promoters} max={n.n} text={String(n.promoters)} />
          <HBar label={t("中立 7–8")} value={n.passives} max={n.n} text={String(n.passives)} tone="warn" />
          <HBar label={t("贬损者 0–6")} value={n.detractors} max={n.n} text={String(n.detractors)} tone="bad" />
        </div>
        <p className="a-muted small">{t("NPS = 推荐者 % − 贬损者 %，范围 −100 到 100。")}</p>
      </Card>
      <Card title={t("每个分数多少人")}>
        <div className="a-npsbars">
          {scores.map((v, i) => (
            <div key={i} title={String(v)}>
              <i style={{ height: `${(v / max) * 100}%` }} className={i >= 9 ? "ok" : i >= 7 ? "warn" : "bad"} />
              <span>{i}</span>
            </div>
          ))}
        </div>
        <div className="a-sep" />
        <Quotes p={p} kind="nps" />
      </Card>
    </div>
  );
}
