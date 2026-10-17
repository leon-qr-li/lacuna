import { useEffect, useRef, useState } from "react";
import { GrowText } from "../../components/GrowText";
import type { Health } from "../../api";
import type { PosterVariant, PosterView as View } from "./api";
import { api } from "../../api";
import { MicButton } from "../../components/MicButton";
import { posterApi } from "./api";

/** 海报: Claude draws several square covers (SVG) from the publish pack, rendered on this machine;
 *  Leon picks one (rendered at 3000×3000 into the publish folder) or changes one with a sentence. */
export function PosterView({ id, flash, onPauseMain }: { id: string; flash: (m: string) => void; onPauseMain: () => void }) {
  const [view, setView] = useState<View | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(Date.now());
  const [health, setHealth] = useState<Health | null>(null);
  const [big, setBig] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  const load = () =>
    posterApi
      .poster(id)
      .then((v) => {
        setView(v);
        if (v.job?.state === "running") timer.current = window.setTimeout(load, 800);
      })
      .catch((e) => setErr(String(e.message ?? e)));

  useEffect(() => {
    void load();
    api.health().then(setHealth, () => setHealth(null));
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const running = view?.job?.state === "running";
  useEffect(() => {
    if (!running) return;
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [running]);

  const act = async (p: Promise<View>) => {
    setBusy(true);
    try {
      const v = await p;
      setView(v);
      if (v.job?.state === "running") timer.current = window.setTimeout(load, 800);
      return true;
    } catch (e) {
      flash(`操作失败：${(e as Error).message}`);
      return false;
    } finally {
      setBusy(false);
    }
  };

  if (err) return <p className="error pad">海报页打不开：{err}</p>;
  if (!view) return <p className="pad muted">加载中…</p>;

  const claude = view.available;
  const job = view.job;
  const n = view.directions.length;
  const chosen = view.variants.find((v) => v.id === view.chosen) ?? null;
  const generate = () => {
    if (view.variants.length && !window.confirm(`再画 ${n} 版？之前的版本都会留着。（会再花一次 Claude 的钱）`)) return;
    void act(posterApi.generatePoster(id));
  };

  return (
    <main className="publish poster">
      <div className="publish-head">
        <div>
          <h1>海报</h1>
          <p className="muted small">
            Claude 按这一集的标题和简介画 {n} 版方形封面（{view.directions.map((d) => d.label).join("、")}），在本机渲染。挑一张，或者说一句话让它改。
          </p>
        </div>
        <span className="grow" />
        <button
          type="button"
          className={view.variants.length ? "btn btn-outline" : "btn btn-primary"}
          onClick={generate}
          disabled={busy || running || !view.has_pack || !claude}
        >
          {view.variants.length ? `再画 ${n} 版` : `画 ${n} 版海报`}
        </button>
      </div>

      {!view.has_pack && (
        <p className="card" data-testid="poster-needs-pack">
          海报按「发布资料」里的标题和简介来画，请先去 <a href={`#/ep/${encodeURIComponent(id)}/publish`}>发布资料</a> 生成一次。
        </p>
      )}
      {view.has_pack && !claude && <p className="card">没有接上 Claude（没找到 ANTHROPIC_API_KEY，或没装 anthropic 包），画不了海报。</p>}
      {view.has_pack && claude && !view.variants.length && !running && (
        <p className="card">只发标题、简介和片名这些文字给 Claude，{n} 版同时画，大约 2–4 分钟，一共约 $1。</p>
      )}
      {running && (
        <p className="card" role="status" data-testid="poster-running">
          {job?.stage}… 已用 {Math.max(0, Math.round((now - (job?.started ?? 0) * 1000) / 1000))} 秒
        </p>
      )}
      {job?.state === "error" && <p className="card error">没成功：{job.error}</p>}
      {view.errors.length > 0 && <p className="card warn small">有几版没画出来：{view.errors.join("；")}</p>}

      {view.cover && chosen && (
        <section className="card cover-card" aria-label="选定的封面" data-testid="poster-cover">
          <img src={posterApi.posterPreview(id, chosen.id)} alt={`选定的封面 ${chosen.name}`} />
          <div className="grow">
            <strong>已选：{chosen.name}</strong>
            <p className="small">
              {view.cover.px}×{view.cover.px} 的封面已经存好，上传喜马拉雅用 <span className="mono">cover.jpg</span>（
              {(view.cover.jpg_bytes / 1024 / 1024).toFixed(1)} MB），<span className="mono">cover.png</span> 是无损备份。
            </p>
            <p className="muted small mono">{view.cover.folder}</p>
            <button type="button" className="btn btn-outline btn-small" onClick={() => api.openExports(id).catch((e) => flash(`打不开文件夹：${e.message}`))}>
              打开文件夹
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
        <div className="poster-zoom" role="dialog" aria-label="大图" onClick={() => setBig(null)}>
          <img src={posterApi.posterPreview(id, big)} alt="大图" />
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
  const [text, setText] = useState("");
  return (
    <article className={`card poster-card${chosen ? " is-chosen" : ""}`} data-testid="poster-card" aria-label={`海报 ${v.name}`}>
      <button type="button" className="poster-img" onClick={props.onBig} title="看大图">
        <img src={posterApi.posterPreview(id, v.id)} alt={v.name} loading="lazy" />
      </button>
      <div className="row wrap gap8">
        <strong className="grow">{v.name}</strong>
        <span className="chip">{v.direction_label}</span>
        {chosen && <span className="chip chip-ok">已选</span>}
      </div>
      {v.instruction && (
        <p className="muted small">
          改自 {v.parent}：「{v.instruction}」
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
          {chosen ? "正在用这张" : "用这张"}
        </button>
        {v.cost_usd ? <span className="muted small">约 ${v.cost_usd.toFixed(2)}</span> : null}
      </div>
      <form
        className="row gap8 align-end"
        onSubmit={async (e) => {
          e.preventDefault();
          if (text.trim() && (await props.onRevise(text.trim()))) setText("");
        }}
      >
        <GrowText
          aria-label={`改一改 ${v.name}`}
          placeholder="一句话改，如：换成暖色"
          value={text}
          onChange={setText}
          disabled={busy}
        />
        <MicButton
          available={!!health?.dictation}
          note={health?.dictation_note}
          disabled={busy}
          onStart={props.onPauseMain}
          onText={(t) => setText((cur) => (cur.trim() ? `${cur.trimEnd()} ${t}` : t))}
          onError={props.flash}
        />
        <button type="submit" className="btn btn-outline btn-small" disabled={busy || !text.trim()}>
          改
        </button>
      </form>
    </article>
  );
}
