import { useEffect, useMemo, useRef, useState } from "react";
import type { PublishView as View } from "./api";
import { copyRich, copyText, markdownToHtml } from "../../markdown";
import { publishApi } from "./api";
import { fmtDateTime, joinList, t } from "../../i18n";
import { BusyLabel, JobProgress, PageLoading } from "../loading/Loading";

/** 发布资料: title, one-line blurb, show notes (Markdown, approved D40 format), chapters and the
 *  names to check, all for the version of the cut that will be published. */
export function PublishView({ id, version, flash }: { id: string; version: string; flash: (m: string) => void }) {
  const [view, setView] = useState<View | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const timer = useRef<number | null>(null);

  const load = () =>
    publishApi
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

  const act = async (p: Promise<View>, msg?: string) => {
    setBusy(true);
    try {
      const v = await p;
      setView(v);
      if (v.job?.state === "running") timer.current = window.setTimeout(load, 800);
      if (msg) flash(msg);
      return true;
    } catch (e) {
      flash(t("操作失败：{message}", { message: (e as Error).message }));
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
      flash(t("复制失败：{message}", { message: (e as Error).message }));
    }
  };

  const pack = view?.pack ?? null;
  const html = useMemo(() => (pack ? markdownToHtml(pack.markdown) : ""), [pack]);

  if (err) return <p className="error pad">{t("发布资料打不开：")}{err}</p>;
  if (!view) return <PageLoading label={t("正在打开发布资料…")} />;

  const generate = () => {
    if (pack && !window.confirm(pack.edited ? t("重新生成会覆盖你手改过的 show notes，确定吗？") : t("重新生成一版？（会再花一次 Claude 的钱）"))) return;
    setEditing(false);
    void act(publishApi.generatePublish(id));
  };
  const claude = view.editor === "claude";
  const job = view.job;

  return (
    <main className="publish">
      <div className="publish-head">
        <div>
          <h1>{t("发布资料")}</h1>
          <p className="muted small">
            {t("标题、简介、show notes 和章节，按现在这版剪辑的成品时间。喜马拉雅是唯一发布源，小宇宙会自动同步。")}
          </p>
        </div>
        <span className="grow" />
        <button type="button" className={pack ? "btn btn-outline" : "btn btn-primary"} onClick={generate} disabled={busy || running}>
          <BusyLabel busy={running} label={pack ? t("重新生成") : t("生成发布资料")} busyLabel={t("生成中…")} />
        </button>
      </div>

      {!pack && !running && (
        <p className="card">
          {claude
            ? t("Claude 会读这一集剪完后的转写（只发文字），写标题、简介和 show notes，大约 1–2 分钟，花费约 $0.2–0.3。")
            : t("没有接上 Claude（{p0}），只能生成按时间切的草稿。", { p0: view.editor_note || t("没找到 API key") })}
        </p>
      )}
      {running && (
        <JobProgress title={t("正在写发布资料")} stage={job?.stage} started={job?.started} typical={90} testId="publish-running" />
      )}
      {job?.state === "error" && <p className="card error">{t("没生成出来：{error}。可以再点一次「生成发布资料」。", { error: job.error })}</p>}

      {pack && (
        <>
          {pack.stale && (
            <div className="banner-card row wrap gap8" data-testid="publish-stale">
              <span className="grow">{pack.library ? t("剪辑在生成之后又改过，时间戳和配乐可能不准了。更新只在本机重新对时间，不花钱，你改过的文字会保留。") : t("剪辑在生成之后又改过，时间戳可能不准了。更新只在本机重新对时间，不花钱，你改过的文字会保留。")}</span>
              <button type="button" className="btn btn-primary btn-small" disabled={busy} onClick={() => act(publishApi.retimePublish(id), t("时间戳已按最新剪辑更新"))}>
                {t("更新时间戳")}
              </button>
            </div>
          )}
          {pack.gone.length > 0 && (
            <p className="card warn small">
              {t("这些条目说的那段话后来被剪掉了，建议删掉或改写：")}{joinList(pack.gone.map((g) => `「${g}」`))}
            </p>
          )}
          {pack.notes.map((n) => (
            <p key={n} className="muted small">
              {n}
            </p>
          ))}

          <section className="card" aria-label={t("标题")}>
            <div className="card-head">
              <strong>{t("标题")}</strong>
              <button type="button" className="btn btn-outline btn-small" onClick={() => copy("text", pack.title, t("标题已复制"))}>
                {t("复制标题")}
              </button>
            </div>
            <p className="publish-title" data-testid="publish-title">
              {pack.title}
            </p>
            {pack.alt_titles.length > 0 && (
              <div className="row wrap gap8">
                <span className="muted small">{t("换一个：")}</span>
                {pack.alt_titles.map((alt) => (
                  <button key={alt} type="button" className="btn btn-outline btn-small" disabled={busy} onClick={() => act(publishApi.editPublish(id, { title: alt }), t("标题已换"))}>
                    {alt}
                  </button>
                ))}
              </div>
            )}
          </section>

          {pack.blurb && (
            <section className="card" aria-label={t("一句话简介")}>
              <div className="card-head">
                <strong>{t("一句话简介")}</strong>
                <button type="button" className="btn btn-outline btn-small" onClick={() => copy("text", pack.blurb, t("简介已复制"))}>
                  {t("复制")}
                </button>
              </div>
              <p>{pack.blurb}</p>
            </section>
          )}

          <section className="card" aria-label="Show notes">
            <div className="card-head">
              <strong>Show notes{pack.edited ? t(" · 已手改") : ""}</strong>
              <span className="row wrap gap8">
                {!editing && (
                  <>
                    <button type="button" className="btn btn-primary btn-small" onClick={() => copy("rich", pack.markdown, t("已复制：带格式的文字 + Markdown 原文，贴到哪都行"))}>
                      {t("复制（带格式）")}
                    </button>
                    <button type="button" className="btn btn-outline btn-small" onClick={() => copy("text", pack.markdown, t("Markdown 原文已复制"))}>
                      {t("复制 Markdown")}
                    </button>
                    <button
                      type="button"
                      className="btn btn-outline btn-small"
                      onClick={() => {
                        setDraft(pack.markdown);
                        setEditing(true);
                      }}
                    >
                      {t("编辑")}
                    </button>
                    {pack.edited && (
                      <button type="button" className="linkish small" disabled={busy} onClick={() => window.confirm(t("丢掉你手改的内容，恢复成生成的版本？")) && act(publishApi.editPublish(id, { markdown: null }), t("已恢复成生成的版本"))}>
                        {t("恢复成生成的版本")}
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
                      onClick={async () => (await act(publishApi.editPublish(id, { markdown: draft }), t("已保存"))) && setEditing(false)}
                    >
                      {t("保存")}
                    </button>
                    <button type="button" className="btn btn-outline btn-small" onClick={() => setEditing(false)}>
                      {t("取消")}
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
            <p className="muted small">{t("也存在 {path}", { path: view.notes_path })}</p>
          </section>

          <section className="card" aria-label={t("章节")}>
            <div className="card-head">
              <strong>{t("章节（成品时间）")}</strong>
              <button
                type="button"
                className="btn btn-outline btn-small"
                onClick={() => copy("text", pack.chapters.map((c) => `${c.time} ${c.heading}`).join("\n"), t("章节已复制"))}
              >
                {t("复制章节")}
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
            <section className="card" aria-label={t("专有名词核对")}>
              <div className="card-head">
                <strong>{t("专有名词核对")}</strong>
                <span className="muted small">{t("转写可能听错的片名和人名。改了会记住，下一集自动用对的写法。")}</span>
              </div>
              <ul className="names">
                {pack.names.map((n) => (
                  <li key={n.heard} data-testid="name-check">
                    <span className="grow">
                      {t("听成「{heard}」→ 应为", { heard: n.heard })} 「<strong>{n.suggested}</strong>」<span className="muted small"> {n.why}</span>
                    </span>
                    {n.state === "open" ? (
                      <span className="row gap8">
                        <button type="button" className="btn btn-primary btn-small" disabled={busy} onClick={() => act(publishApi.publishName(id, n.heard, "apply"), t("已全部改成「{suggested}」", { suggested: n.suggested }))}>
                          {t("改成「{suggested}」", { suggested: n.suggested })}
                        </button>
                        <button type="button" className="btn btn-outline btn-small" disabled={busy} onClick={() => act(publishApi.publishName(id, n.heard, "ignore"))}>
                          {t("不用改")}
                        </button>
                      </span>
                    ) : (
                      <span className="chip">{n.state === "applied" ? t("已改") : t("不改")}</span>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}

          <p className="muted small">
            {pack.adapter === "claude" ? t("Claude 写的") : t("规则草稿（没有 Claude）")}
            {pack.usage?.cost_usd ? t(" · 约 ${p0}", { p0: pack.usage.cost_usd.toFixed(2) }) : ""} {t("· 生成于 {time}", { time: fmtDateTime(pack.generated_at) })}
          </p>
        </>
      )}
    </main>
  );
}
