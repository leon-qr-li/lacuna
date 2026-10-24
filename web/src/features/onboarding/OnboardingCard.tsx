import { useState } from "react";
import { lang, t } from "../../i18n";
import { confirmDialog } from "../dialog/Dialog";
import { loadProjects } from "../projects/api";
import { onboardingApi, openSample, setOnboarding, useOnboarding } from "./api";

/** 设置 → 通用: add, open or delete LACUNA 示例节目 (its bubble tour replays from there). */
export function OnboardingCard() {
  const ob = useOnboarding();
  const [err, setErr] = useState<string | null>(null);
  if (!ob) return null;
  const fail = (e: unknown) => setErr((e as Error).message);
  const drop = async () => {
    if (!(await confirmDialog({ message: t("删掉示例节目？以后随时可以在这里重新添加。"), danger: true, confirmLabel: t("删除") }))) return;
    onboardingApi.dropSample().then((o) => {
      setOnboarding(o);
      void loadProjects(true);
    }, fail);
  };
  return (
    <section className="card" aria-label={t("入门引导")} data-testid="onboard-settings">
      <h2>{t("入门引导")}</h2>
      <div className="row gap8 wrap">
        <button type="button" className="btn btn-outline" onClick={() => void openSample(lang).catch(fail)} data-testid="sample-open">
          {ob.sample ? t("打开示例节目") : t("添加示例节目")}
        </button>
        {ob.sample && (
          <button type="button" className="btn btn-ghost" onClick={() => void drop()} data-testid="sample-drop">
            {t("删除示例节目")}
          </button>
        )}
      </div>
      <p className="muted small">{t("示例节目是一集剪好第一刀的示例，给你练手，不占用额度和节目数。")}</p>
      {err && <p className="error">{err}</p>}
    </section>
  );
}
