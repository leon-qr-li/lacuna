import { useState } from "react";
import { t } from "../../i18n";
import { confirmDialog } from "../dialog/Dialog";
import { openProject, useProjects } from "../projects/api";
import { onboardingApi, useOnboarding, type SampleStep } from "./api";

const KEY = "lacuna.coach";

function info(s: SampleStep): { label: string; hint: string; mode: string } {
  switch (s) {
    case "ab":
      return { label: t("听一处删减"), hint: t("先按 A 听原话，再按 B 听剪后的。删减已经生效，你只需要决定要不要。"), mode: "review" };
    case "decide":
      return { label: t("保留或恢复"), hint: t("觉得删得对就按 K（保留）；想要回原话就按 R（恢复）。"), mode: "review" };
    case "chat":
      return { label: t("整集试听，对 LACUNA 说一句"), hint: t("在「整集试听」右侧对 LACUNA 说，比如「把那段长停顿再缩短一点」。"), mode: "listen" };
    case "music":
      return { label: t("加上片头和片尾"), hint: t("在「配乐」里放进片头和片尾音乐。"), mode: "music" };
    case "export":
      return { label: t("导出，下载成品"), hint: t("在「导出」里点「下载 MP3」。"), mode: "export" };
  }
}

/** The coach panel in LACUNA 示例节目 (new-user batch, recommended C): one step at a time, ticked when you
 *  really did it; at the end, the way to your own first episode. Only in the sample show. */
export function Coach() {
  const ob = useOnboarding();
  const sp = useProjects();
  const [small, setSmall] = useState(() => {
    try {
      return localStorage.getItem(KEY) === "small";
    } catch {
      return false;
    }
  });
  if (!ob?.sample || !sp?.current?.sample) return null;
  const steps = ob.sample_steps;
  const done = (s: SampleStep) => ob.done.includes(`sample.${s}`);
  const n = steps.filter(done).length;
  const next = steps.find((s) => !done(s));
  const epid = ob.sample.episode;
  const own = sp.mine.find((m) => !m.sample && !m.archived && !m.support);
  const fold = (v: boolean) => {
    setSmall(v);
    try {
      localStorage.setItem(KEY, v ? "small" : "open");
    } catch {
      /* private mode */
    }
  };
  const reset = async () => {
    if (!(await confirmDialog({ message: t("示例集会回到 AI 第一刀刚做完的样子，你在里面做的改动都会清掉。"), confirmLabel: t("重置示例") }))) return;
    await onboardingApi.resetSample();
    window.location.hash = `#/ep/${encodeURIComponent(epid)}/review`;
    window.location.reload();
  };
  const leave = () => (own ? void openProject(own.id) : (window.location.hash = "#/projects"));
  if (small)
    return (
      <button type="button" className="coach-pill" onClick={() => fold(false)} data-testid="coach-open">
        {t("示例教程 {n}/{total}", { n, total: steps.length })}
      </button>
    );
  return (
    <aside className="coach" aria-label={t("示例教程")} data-testid="coach">
      <header className="coach-head">
        <strong>{t("示例教程")}</strong>
        <span className="muted small">{n}/{steps.length}</span>
        <span className="grow" />
        <button type="button" className="btn btn-ghost btn-small" onClick={() => fold(true)} aria-label={t("收起教程")}>
          —
        </button>
      </header>
      <p className="muted small coach-note">{t("示例节目 · 不占用你的额度。录音是占位音频，正式示例正在录制。")}</p>
      <ol className="coach-steps">
        {steps.map((s) => {
          const i = info(s);
          return (
            <li key={s} className={done(s) ? "is-done" : s === next ? "is-next" : ""} data-step={s}>
              <span className="onboard-tick" aria-hidden="true">{done(s) ? "✓" : ""}</span>
              <span className="grow">
                {s === next ? <a href={`#/ep/${encodeURIComponent(epid)}/${i.mode}`}>{i.label}</a> : i.label}
                {s === next && <span className="small coach-hint">{i.hint}</span>}
              </span>
            </li>
          );
        })}
      </ol>
      {!next && <p className="coach-hint" data-testid="coach-done">{t("示例走完了。现在导入你自己的第一集吧。")}</p>}
      <div className="row gap8 coach-foot">
        <button type="button" className={`btn btn-small ${next ? "btn-outline" : "btn-primary"}`} onClick={leave} data-testid="coach-own">
          {t("导入我自己的第一集")}
        </button>
        <span className="grow" />
        <button type="button" className="btn btn-ghost btn-small" onClick={() => void reset()} data-testid="coach-reset">
          {t("重置示例")}
        </button>
      </div>
    </aside>
  );
}
