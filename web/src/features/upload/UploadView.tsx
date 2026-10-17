import { useEffect, useState } from "react";
import { api } from "../../api";
import { copyRich, copyText } from "../../markdown";
import type { PublishView } from "../publish/api";
import { publishApi } from "../publish/api";
import type { UploadView as View } from "./api";
import { uploadApi } from "./api";

const mb = (b: number) => `${(b / 1024 / 1024).toFixed(b >= 100 * 1024 * 1024 ? 0 : 1)} MB`;

/** 上传喜马拉雅: everything for the 喜马拉雅 upload form on one page, in the form's order. Leon uploads
 *  by hand (no upload API for personal creators); this page only gathers what other tabs made. */
export function UploadView({ id, version, flash }: { id: string; version: string; flash: (m: string) => void }) {
  const [view, setView] = useState<View | null>(null);
  const [pub, setPub] = useState<PublishView | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([uploadApi.upload(id), publishApi.publish(id)])
      .then(([u, p]) => {
        setView(u);
        setPub(p);
      })
      .catch((e) => setErr(String(e.message ?? e)));
  }, [id, version]);

  const copy = async (rich: boolean, text: string, msg: string) => {
    try {
      await (rich ? copyRich(text) : copyText(text));
      flash(msg);
    } catch (e) {
      flash(`复制失败：${(e as Error).message}`);
    }
  };

  if (err) return <p className="error pad">上传页打不开：{err}</p>;
  if (!view || !pub) return <p className="pad muted">加载中…</p>;

  const tab = (mode: string) => `#/ep/${encodeURIComponent(id)}/${mode}`;
  const pack = pub.pack;
  const missing = [!view.audio && "WAV", !pack && "发布资料", !view.cover && "封面"].filter(Boolean) as string[];
  const stale = [view.audio?.stale && "WAV", pack?.stale && "show notes 的时间戳"].filter(Boolean) as string[];

  return (
    <main className="upload">
      <div>
        <h1>上传喜马拉雅</h1>
        <p className="muted small">
          按喜马拉雅上传页的顺序排好了：下载音频、复制标题和简介、下载封面，你自己上传。小宇宙会从喜马拉雅自动同步。
        </p>
      </div>

      <div className={view.ready ? "card" : "banner-card"} role="status" data-testid="upload-summary">
        {view.ready ? (
          <span>✓ 都准备好了。</span>
        ) : (
          <span>
            {missing.length > 0 && <>还差：{missing.join("、")}。</>}
            {stale.length > 0 && <>剪辑后来又改过，{stale.join("和")}已经不是最新的。</>}
          </span>
        )}{" "}
        <a href={view.upload_page} target="_blank" rel="noreferrer">
          打开喜马拉雅创作中心 ↗
        </a>
      </div>

      <section className="card upload-step" aria-label="音频">
        <div className="card-head">
          <strong className="upload-h"><span className="step-n" aria-hidden="true">1</span>音频（WAV）</strong>
        </div>
        {view.audio ? (
          <>
            <p className="mono small" data-testid="upload-wav">
              {view.audio.name} · {mb(view.audio.bytes)}
              {view.audio.exported_at ? ` · 导出于 ${new Date(view.audio.exported_at).toLocaleString()}` : ""}
            </p>
            {view.audio.stale && <p className="warn small">这个 WAV 是剪辑改动之前导出的。点上方的「导出」再导一次。</p>}
            <div className="row wrap gap8">
              <a className="btn btn-primary btn-small" href={uploadApi.wavUrl(id, view.audio.name)} download={view.audio.name}>
                下载 WAV
              </a>
              <button
                type="button"
                className="btn btn-outline btn-small"
                onClick={() => api.openExports(id).then((r) => flash(`已打开 ${r.folder}`), (e) => flash(`打不开：${e.message}`))}
              >
                打开所在文件夹
              </button>
            </div>
          </>
        ) : (
          <p className="upload-missing">还没导出 WAV。点上方的「导出」，勾上 WAV。</p>
        )}
      </section>

      <section className="card upload-step" aria-label="标题">
        <div className="card-head">
          <strong className="upload-h"><span className="step-n" aria-hidden="true">2</span>标题</strong>
          {pack && (
            <button type="button" className="btn btn-outline btn-small" onClick={() => copy(false, pack.title, "标题已复制")}>
              复制标题
            </button>
          )}
        </div>
        {pack ? (
          <p className="upload-title" data-testid="upload-title">
            {pack.title}
          </p>
        ) : (
          <p className="upload-missing">
            还没有发布资料。去 <a href={tab("publish")}>发布资料</a> 生成。
          </p>
        )}
      </section>

      <section className="card upload-step" aria-label="简介">
        <div className="card-head">
          <strong className="upload-h"><span className="step-n" aria-hidden="true">3</span>简介（show notes）</strong>
          {pack && (
            <span className="row wrap gap8">
              <button type="button" className="btn btn-primary btn-small" onClick={() => copy(true, pack.markdown, "show notes 已复制（带格式），直接贴进简介框")}>
                复制 show notes
              </button>
              {pack.blurb && (
                <button type="button" className="btn btn-outline btn-small" onClick={() => copy(false, pack.blurb, "一句话简介已复制")}>
                  复制一句话简介
                </button>
              )}
            </span>
          )}
        </div>
        {pack ? (
          <>
            {pack.blurb && <p data-testid="upload-blurb">{pack.blurb}</p>}
            {pack.stale && (
              <p className="warn small">
                剪辑后来又改过，时间戳可能不准。去 <a href={tab("publish")}>发布资料</a> 点「更新时间戳」（本机算，不花钱）。
              </p>
            )}
            <p className="muted small">想先改文字，去 <a href={tab("publish")}>发布资料</a> 编辑。</p>
          </>
        ) : (
          <p className="upload-missing">生成发布资料后这里就能复制。</p>
        )}
      </section>

      <section className="card upload-step" aria-label="封面">
        <div className="card-head">
          <strong className="upload-h"><span className="step-n" aria-hidden="true">4</span>封面</strong>
        </div>
        {view.cover ? (
          <div className="upload-cover-row">
            <img className="upload-cover" src={uploadApi.coverUrl(id, view.cover.rendered_at)} alt="本期封面" />
            <div className="upload-col">
              <span className="muted small">
                {view.cover.px}×{view.cover.px} JPG · {mb(view.cover.bytes)}
              </span>
              <a className="btn btn-primary btn-small" href={uploadApi.coverUrl(id, view.cover.rendered_at)} download={`${id}_cover.jpg`}>
                下载封面
              </a>
            </div>
          </div>
        ) : (
          <p className="upload-missing">
            还没选封面。去 <a href={tab("poster")}>海报</a> 画一版，点「用这张」。
          </p>
        )}
      </section>

      <p className="muted small">最后在喜马拉雅上选专辑「洛城二三事」，确认后发布。</p>
    </main>
  );
}
