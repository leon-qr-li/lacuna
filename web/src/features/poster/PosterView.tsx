import { useEffect, useRef, useState } from "react";
import type { Health } from "../../api";
import type { PosterVariant, PosterView as View } from "./api";
import { api } from "../../api";
import { PromptBar } from "../../components/PromptBar";
import { posterApi } from "./api";
import { joinList, lang, t } from "../../i18n";
import { BusyLabel, JobProgress, PageLoading } from "../loading/Loading";
import { confirmDialog } from "../dialog/Dialog";

/** 海报: the AI (LACUNA to Leon) draws several square covers (SVG) from the publish pack, rendered on this machine;
 *  Leon picks one (rendered at 3000×3000 into the publish folder) or changes one with a sentence. */
export function PosterView({ id, flash, onPauseMain }: { id: string; flash: (m: string) => void; onPauseMain: () => void }) {
  const [view, setView] = useState<View | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [health, setHealth] = useState<Health | null>(null);
  const [big, setBig] = useState<string | null>(null);
  const timer = useRef<number | null>(null);
  const shown = useRef<string | null>(id); // the episode on screen; null once the page is gone

  // one polling chain at most, and none after the page is left or another episode is opened
  // (an answer still on its way then must not show or poll again)
  const poll = (v: View) => {
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = v.job?.state === "running" ? window.setTimeout(load, 800) : null;
  };
  const load = () =>
    posterApi
      .poster(id)
      .then((v) => {
        if (shown.current !== id) return;
        setView(v);
        poll(v);
      })
      .catch((e) => shown.current === id && setErr(String(e.message ?? e)));

  useEffect(() => {
    shown.current = id;
    void load();
    api.health().then(setHealth, () => setHealth(null));
    return () => {
      shown.current = null;
      if (timer.current) window.clearTimeout(timer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const running = view?.job?.state === "running";

  const act = async (p: Promise<View>) => {
    setBusy(true);
    try {
      const v = await p;
      if (shown.current !== id) return true;
      setView(v);
      poll(v);
      return true;
    } catch (e) {
      flash(t("操作失败：{message}", { message: (e as Error).message }));
      return false;
    } finally {
      setBusy(false);
    }
  };

  if (err) return <p className="error pad">{t("封面页打不开：")}{err}</p>;
  if (!view) return <PageLoading label={t("正在打开封面…")} shape="cards" />;

  const claude = view.available;
  const job = view.job;
  const n = view.directions.length;
  const chosen = view.variants.find((v) => v.id === view.chosen) ?? null;
  // rounds of 「画 N 版」 are included in the plan, a few per episode (null: no cap)
  const left = view.rounds_left;
  const spent = left === 0;
  const generate = async () => {
    if (view.variants.length && !(await confirmDialog({ message: left == null ? t("再画 {n} 版？之前的版本都会留着。", { n }) : t("再画 {n} 版？之前的版本都会留着。本集还能画 {left} 轮。", { n, left }), confirmLabel: t("再画") }))) return;
    void act(posterApi.generatePoster(id));
  };

  return (
    <main className="publish poster">
      <div className="publish-head">
        <div>
          <h1>{t("封面")}</h1>
          <p className="muted small">
            {t("LACUNA 按这一集的标题和简介画 {n} 版方形封面（{styles}）。挑一张，或者说一句话让它改。", { n, styles: joinList(view.directions.map((d) => d.label)) })}
          </p>
        </div>
        <span className="grow" />
        <button
          type="button"
          className={view.variants.length ? "btn btn-outline" : "btn btn-primary"}
          onClick={generate}
          disabled={busy || running || !view.has_pack || !claude || spent}
          data-tour="poster-generate"
          data-testid="poster-generate"
        >
          <BusyLabel busy={running} label={spent ? t("本集封面次数用完") : view.variants.length ? t("再画 {n} 版", { n }) : t("画 {n} 版封面", { n })} busyLabel={t("正在画…")} />
        </button>
      </div>

      {!view.has_pack && (
        <p className="card" data-testid="poster-needs-pack">
          {t("封面按「发布资料」里的标题和简介来画，请先去")} <a href={`#/ep/${encodeURIComponent(id)}/publish`}>{t("发布资料")}</a> {t("生成一次。")}
        </p>
      )}
      {view.has_pack && !claude && <p className="card">{t("还没接上 AI（没有 AI 密钥），画不了封面。")}</p>}
      {view.has_pack && claude && !view.variants.length && !running && (
        <p className="card">{t("只发标题、简介和片名这些文字给 LACUNA，{n} 版同时画，大约 2–4 分钟。每集可以画 {m} 轮。", { n, m: view.max_rounds })}</p>
      )}
      {running && (
        <JobProgress
          title={job?.kind === "revise" ? t("正在按你的话改封面") : job?.kind === "choose" ? t("正在准备选定的封面") : t("正在画 {n} 版封面", { n })}
          stage={job?.stage}
          started={job?.started}
          typical={job?.kind === "choose" ? 15 : job?.kind === "revise" ? 90 : 180}
          testId="poster-running"
        />
      )}
      {job?.state === "error" && <p className="card error">{t("没成功：{error}", { error: job.error })}</p>}
      {view.errors.length > 0 && <p className="card warn small">{t("有几版没画出来：{errors}", { errors: view.errors.join(lang === "en" ? "; " : "；") })}</p>}

      {view.cover && chosen && (
        <section className="card cover-card" aria-label={t("选定的封面")} data-testid="poster-cover">
          <img src={posterApi.posterPreview(id, chosen.id)} alt={t("选定的封面 {name}", { name: chosen.name })} />
          <div className="grow">
            <strong>{t("已选：{name}", { name: chosen.name })}</strong>
            <p className="small">
              {t("{px}×{px} 的封面已经存好，上传喜马拉雅用 cover.jpg（{mb} MB），cover.png 是无损备份。", {
                px: view.cover.px,
                mb: (view.cover.jpg_bytes / 1024 / 1024).toFixed(1),
              })}
            </p>
            <p className="muted small mono">{view.cover.folder}</p>
            <button type="button" className="btn btn-outline btn-small" onClick={() => api.openExports(id).catch((e) => flash(t("打不开文件夹：{message}", { message: e.message })))}>
              {t("打开文件夹")}
            </button>
          </div>
        </section>
      )}

      {view.variants.length > 0 && (
        <div className="poster-grid">
          {view.variants.map((v) => (
            <PosterCard
              key={v.id}
              id={id}
              v={v}
              chosen={v.id === view.chosen}
              busy={busy || running}
              health={health}
              onBig={() => setBig(v.id)}
              onChoose={() => act(posterApi.choosePoster(id, v.id))}
              onRevise={(text) => act(posterApi.revisePoster(id, v.id, text))}
              onPauseMain={onPauseMain}
              flash={flash}
            />
          ))}
        </div>
      )}

      {big && (
        <div className="poster-zoom" role="dialog" aria-label={t("大图")} onClick={() => setBig(null)}>
          <img src={posterApi.posterPreview(id, big)} alt={t("大图")} />
        </div>
      )}
    </main>
  );
}

function PosterCard(props: {
  id: string;
  v: PosterVariant;
  chosen: boolean;
  busy: boolean;
  health: Health | null;
  onBig: () => void;
  onChoose: () => Promise<boolean>;
  onRevise: (text: string) => Promise<boolean>;
  onPauseMain: () => void;
  flash: (m: string) => void;
}) {
  const { id, v, chosen, busy, health } = props;
  return (
    <article className={`card poster-card${chosen ? " is-chosen" : ""}`} data-testid="poster-card" aria-label={t("封面 {name}", { name: v.name })}>
      <button type="button" className="poster-img" onClick={props.onBig} title={t("看大图")}>
        <img src={posterApi.posterPreview(id, v.id)} alt={v.name} loading="lazy" />
      </button>
      <div className="row wrap gap8">
        <strong className="grow">{v.name}</strong>
        <span className="chip">{v.direction_label}</span>
        {chosen && <span className="chip chip-ok">{t("已选")}</span>}
      </div>
      {v.instruction && (
        <p className="muted small">
          {t("改自 {parent}：「{instruction}」", { parent: v.parent, instruction: v.instruction })}
        </p>
      )}
      <p className="small">{v.concept}</p>
      {v.notes.map((n) => (
        <p key={n} className="muted small">
          {n}
        </p>
      ))}
      <div className="row gap8">
        <button type="button" className="btn btn-primary btn-small" disabled={busy || chosen} onClick={() => void props.onChoose()}>
          {chosen ? t("正在用这张") : t("用这张")}
        </button>
      </div>
      <PromptBar
        label={t("改一改 {name}", { name: v.name })}
        placeholder={t("一句话改，如：换成暖色")}
        submitLabel={t("改")}
        hint={t("Enter 发送 · Shift+Enter 换行")}
        disabled={busy}
        mic={{ available: !!health?.dictation, note: health?.dictation_note, onStart: props.onPauseMain, onError: props.flash,
          context: () => ({ episode: id, where: "poster" }) }}
        onSubmit={props.onRevise}
        testId="poster-revise"
      />
    </article>
  );
}
