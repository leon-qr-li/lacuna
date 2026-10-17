import { useEffect, useMemo, useRef, useState } from "react";
import type { PublishView as View } from "../api";
import { api } from "../api";
import { copyRich, copyText, markdownToHtml } from "../markdown";

/** 发布资料: title, one-line blurb, show notes (Markdown, approved D40 format), chapters and the
 *  names to check, all for the version of the cut that will be published. */
export function PublishView({ id, version, flash }: { id: string; version: string; flash: (m: string) => void }) {
  const [view, setView] = useState<View | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(Date.now());
  const timer = useRef<number | null>(null);

  const load = () =>
    api
      .publish(id)
      .then((v) => {
        setView(v);
        if (v.job?.state === "running") timer.current = window.setTimeout(load, 800);
      })
      .catch((e) => setErr(String(e.message ?? e)));

  // reload when the cut changes, so "stale" shows up right after an edit
  useEffect(() => {
    void load();
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, version]);

  const running = view?.job?.state === "running";
  useEffect(() => {
    if (!running) return;
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [running]);

  const act = async (p: Promise<View>, msg?: string) => {
    setBusy(true);
    try {
      const v = await p;
      setView(v);
      if (v.job?.state === "running") timer.current = window.setTimeout(load, 800);
      if (msg) flash(msg);
      return true;
    } catch (e) {
      flash(`操作失败：${(e as Error).message}`);
      return false;
    } finally {
      setBusy(false);
    }
  };

  const copy = async (what: "rich" | "md" | "text", text: string, msg: string) => {
    try {
      await (what === "rich" ? copyRich(text) : copyText(text));
      flash(msg);
    } catch (e) {
      flash(`复制失败：${(e as Error).message}`);
    }
  };

  const pack = view?.pack ?? null;
  const html = useMemo(() => (pack ? markdownToHtml(pack.markdown) : ""), [pack]);

  if (err) return <p className="error pad">发布资料打不开：{err}</p>;
  if (!view) return <p className="pad muted">加载中…</p>;

  const generate = () => {
    if (pack && !window.confirm(pack.edited ? "重新生成会覆盖你手改过的 show notes，确定吗？" : "重新生成一版？（会再花一次 Claude 的钱）")) return;
    setEditing(false);
    void act(api.generatePublish(id));
  };
  const claude = view.editor === "claude";
  const job = view.job;

  return (
    <main className="publish">
      <div className="publish-head">
        <div>
          <h1>发布资料</h1>
          <p className="muted small">
            标题、简介、show notes 和章节，按现在这版剪辑的成品时间。喜马拉雅是唯一发布源，小宇宙会自动同步。
          </p>
        </div>
        <span className="grow" />
        <button type="button" className={pack ? "btn btn-outline" : "btn btn-primary"} onClick={generate} disabled={busy || running}>
          {pack ? "重新生成" : "生成发布资料"}
        </button>
      </div>

      {!pack && !running && (
        <p className="card">
          {claude
            ? "Claude 会读这一集剪完后的转写（只发文字），写标题、简介和 show notes，大约 1–2 分钟，花费约 $0.2–0.3。"
            : `没有接上 Claude（${view.editor_note || "没找到 API key"}），只能生成按时间切的草稿。`}
        </p>
      )}
      {running && (
        <p className="card" role="status" data-testid="publish-running">
          {job?.stage}… 已用 {Math.max(0, Math.round((now - (job?.started ?? 0) * 1000) / 1000))} 秒
        </p>
      )}
      {job?.state === "error" && <p className="card error">没生成出来：{job.error}。可以再点一次「生成发布资料」。</p>}

      {pack && (
        <>
          {pack.stale && (
            <div className="banner-card row wrap gap8" data-testid="publish-stale">
              <span className="grow">剪辑在生成之后又改过，时间戳{pack.library ? "和配乐" : ""}可能不准了。更新只在本机重新对时间，不花钱，你改过的文字会保留。</span>
              <button type="button" className="btn btn-primary btn-small" disabled={busy} onClick={() => act(api.retimePublish(id), "时间戳已按最新剪辑更新")}>
                更新时间戳
              </button>
            </div>
          )}
          {pack.gone.length > 0 && (
            <p className="card warn small">
              这些条目说的那段话后来被剪掉了，建议删掉或改写：{pack.gone.map((g) => `「${g}」`).join("、")}
            </p>
          )}
          {pack.notes.map((n) => (
            <p key={n} className="muted small">
              {n}
            </p>
          ))}

          <section className="card" aria-label="标题">
            <div className="card-head">
              <strong>标题</strong>
              <button type="button" className="btn btn-outline btn-small" onClick={() => copy("text", pack.title, "标题已复制")}>
                复制标题
              </button>
            </div>
            <p className="publish-title" data-testid="publish-title">
              {pack.title}
            </p>
            {pack.alt_titles.length > 0 && (
              <div className="row wrap gap8">
                <span className="muted small">换一个：</span>
                {pack.alt_titles.map((t) => (
                  <button key={t} type="button" className="btn btn-outline btn-small" disabled={busy} onClick={() => act(api.editPublish(id, { title: t }), "标题已换")}>
                    {t}
                  </button>
                ))}
              </div>
            )}
          </section>

          {pack.blurb && (
            <section className="card" aria-label="一句话简介">
              <div className="card-head">
                <strong>一句话简介</strong>
                <button type="button" className="btn btn-outline btn-small" onClick={() => copy("text", pack.blurb, "简介已复制")}>
                  复制
                </button>
              </div>
              <p>{pack.blurb}</p>
            </section>
          )}

          <section className="card" aria-label="Show notes">
            <div className="card-head">
              <strong>Show notes{pack.edited ? " · 已手改" : ""}</strong>
              <span className="row wrap gap8">
                {!editing && (
                  <>
                    <button type="button" className="btn btn-primary btn-small" onClick={() => copy("rich", pack.markdown, "已复制：带格式的文字 + Markdown 原文，贴到哪都行")}>
                      复制（带格式）
                    </button>
                    <button type="button" className="btn btn-outline btn-small" onClick={() => copy("text", pack.markdown, "Markdown 原文已复制")}>
                      复制 Markdown
                    </button>
                    <button
                      type="button"
                      className="btn btn-outline btn-small"
                      onClick={() => {
                        setDraft(pack.markdown);
                        setEditing(true);
                      }}
                    >
                      编辑
                    </button>
                    {pack.edited && (
                      <button type="button" className="linkish small" disabled={busy} onClick={() => window.confirm("丢掉你手改的内容，恢复成生成的版本？") && act(api.editPublish(id, { markdown: null }), "已恢复成生成的版本")}>
                        恢复成生成的版本
                      </button>
                    )}
                  </>
                )}
                {editing && (
                  <>
                    <button
                      type="button"
                      className="btn btn-primary btn-small"
                      disabled={busy}
                      onClick={async () => (await act(api.editPublish(id, { markdown: draft }), "已保存")) && setEditing(false)}
                    >
                      保存
                    </button>
                    <button type="button" className="btn btn-outline btn-small" onClick={() => setEditing(false)}>
                      取消
                    </button>
                  </>
                )}
              </span>
            </div>
            {editing ? (
              <textarea className="md-edit mono" aria-label="Markdown" value={draft} onChange={(e) => setDraft(e.target.value)} />
            ) : (
              <article className="md" data-testid="show-notes" dangerouslySetInnerHTML={{ __html: html }} />
            )}
            <p className="muted small">也存在 {view.notes_path}</p>
          </section>

          <section className="card" aria-label="章节">
            <div className="card-head">
              <strong>章节（成品时间）</strong>
              <button
                type="button"
                className="btn btn-outline btn-small"
                onClick={() => copy("text", pack.chapters.map((c) => `${c.time} ${c.heading}`).join("\n"), "章节已复制")}
              >
                复制章节
              </button>
            </div>
            <ol className="chapters">
              {pack.chapters.map((c) => (
                <li key={c.heading + c.t}>
                  <span className="mono">{c.time}</span> {c.heading}
                </li>
              ))}
            </ol>
          </section>

          {pack.names.length > 0 && (
            <section className="card" aria-label="专有名词核对">
              <div className="card-head">
                <strong>专有名词核对</strong>
                <span className="muted small">转写可能听错的片名和人名。改了会记住，下一集自动用对的写法。</span>
              </div>
              <ul className="names">
                {pack.names.map((n) => (
                  <li key={n.heard} data-testid="name-check">
                    <span className="grow">
                      听成「{n.heard}」→ 应为「<strong>{n.suggested}</strong>」<span className="muted small"> {n.why}</span>
                    </span>
                    {n.state === "open" ? (
                      <span className="row gap8">
                        <button type="button" className="btn btn-primary btn-small" disabled={busy} onClick={() => act(api.publishName(id, n.heard, "apply"), `已全部改成「${n.suggested}」`)}>
                          改成「{n.suggested}」
                        </button>
                        <button type="button" className="btn btn-outline btn-small" disabled={busy} onClick={() => act(api.publishName(id, n.heard, "ignore"))}>
                          不用改
                        </button>
                      </span>
                    ) : (
                      <span className="chip">{n.state === "applied" ? "已改" : "不改"}</span>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}

          <p className="muted small">
            {pack.adapter === "claude" ? "Claude 写的" : "规则草稿（没有 Claude）"}
            {pack.usage?.cost_usd ? ` · 约 $${pack.usage.cost_usd.toFixed(2)}` : ""} · 生成于 {new Date(pack.generated_at).toLocaleString()}
          </p>
        </>
      )}
    </main>
  );
}
