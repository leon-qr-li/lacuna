import { useEffect } from "react";
import type { EpisodeListItem } from "../../api";
import { t } from "../../i18n";
import type { Show } from "../show/api";
import { useProjects } from "../projects/api";
import { markStep, onboardingApi, setOnboarding, useOnboarding, type Onboarding, type Step } from "./api";

const ep = (id: string | undefined, mode: string) => (id ? `#/ep/${encodeURIComponent(id)}/${mode}` : "#/");

/** What each step of your own first episode says, and where it takes you. */
function stepInfo(s: Step, first: string | undefined): { label: string; hint: string; href: string } {
  switch (s) {
    case "show":
      return { label: t("建好节目"), hint: t("节目名字、语言和每位主持人"), href: "#/" };
    case "import":
      return { label: t("导入第一集"), hint: t("每位主持人一条分轨；导入完成后 LACUNA 自动剪第一刀"), href: "#/" };
    case "review":
      return { label: t("审阅 AI 第一刀"), hint: t("听 A/B 对比，决定保留还是恢复（过目至少 3 处）"), href: ep(first, "review") };
    case "chat":
      return { label: t("整集试听，对 LACUNA 说一句修改"), hint: t("比如「把这里的停顿再缩短一点」"), href: ep(first, "listen") };
    case "music":
      return { label: t("加片头和片尾音乐"), hint: t("在「配乐」里放进片头和片尾"), href: ep(first, "music") };
    case "export":
      return { label: t("导出并下载成品"), hint: t("在「导出」里下载 MP3 或 WAV"), href: ep(first, "export") };
  }
}

export const progress = (o: Onboarding) => o.steps.filter((s) => o.done.includes(s)).length;

/** 入门清单 on 首页 (new-user batch, recommended C + A): your first episode from import to download. Each step
 *  ticks itself when the real thing happens; 隐藏 puts it away (设置 → 通用 brings it back). */
export function Checklist({ show, episodes }: { show: Show | null; episodes: EpisodeListItem[] | null }) {
  const ob = useOnboarding();
  const cur = useProjects()?.current;
  const sample = !!cur?.sample;
  const setUp = !!show && !show.needs_setup;
  const first = episodes?.find((e) => !e.error)?.id;
  // the steps that home itself can see happened
  useEffect(() => {
    if (!ob || sample || ob.collab) return;
    if (setUp) markStep("show");
    if (first) markStep("import");
  }, [ob, sample, setUp, first]);
  if (!ob || ob.hidden || sample || (!setUp && !ob.collab)) return null;
  const n = progress(ob);
  const total = ob.steps.length;
  const next = ob.steps.find((s) => !ob.done.includes(s));
  const hide = () => void onboardingApi.flags({ hidden: true }).then(setOnboarding, () => undefined);
  return (
    <section className="card onboard" aria-label={t("入门")} data-testid="onboard-card">
      <div className="card-head">
        <h2>
          {ob.collab ? t("{by} 邀请你一起剪《{show}》", ob.collab) : t("入门")}{" "}
          <span className="muted small" data-testid="onboard-progress">
            {n}/{total}
          </span>
        </h2>
        <button type="button" className="btn btn-ghost btn-small" onClick={hide} data-testid="onboard-hide">
          {next ? t("隐藏") : t("收起")}
        </button>
      </div>
      {!next ? (
        <p className="muted" data-testid="onboard-done">{t("入门都完成了。以后每一集都是这几步。")}</p>
      ) : (
        <ol className="onboard-steps">
          {ob.steps.map((s) => {
            const info = stepInfo(s, first);
            const done = ob.done.includes(s);
            return (
              <li key={s} className={done ? "is-done" : s === next ? "is-next" : ""} data-step={s}>
                <span className="onboard-tick" aria-hidden="true">{done ? "✓" : ""}</span>
                <span className="grow">
                  {s === next ? <a href={info.href}>{info.label}</a> : info.label}
                  {s === next && <span className="muted small onboard-hint">{info.hint}</span>}
                </span>
                {done && <span className="sr-only">{t("已完成")}</span>}
              </li>
            );
          })}
        </ol>
      )}
      {!ob.collab && next && (
        <p className="muted small onboard-extra">
          {t("可选：")}
          <a href="#/project">{t("告诉 LACUNA 节目聊什么")}</a>
        </p>
      )}
    </section>
  );
}

/** The top-bar tag "入门 2/6" on the other screens while the guide is unfinished. */
export function OnboardTag() {
  const ob = useOnboarding();
  const cur = useProjects()?.current;
  if (!ob || ob.hidden || cur?.sample || !ob.welcomed && !ob.collab) return null;
  const n = progress(ob);
  if (n >= ob.steps.length) return null;
  return (
    <a className="btn btn-ghost btn-small onboard-tag" href="#/" data-testid="onboard-tag" title={t("入门清单在首页")}>
      {t("入门 {n}/{total}", { n, total: ob.steps.length })}
    </a>
  );
}
