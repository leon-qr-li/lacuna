import { useEffect, useState, type ReactNode } from "react";
import { lang, t } from "../../i18n";
import { authApi, type AuthStatus } from "../auth/api";
import { plansApi, type MyPlan } from "../plans/api";
import { onboardingApi, openSample, setOnboarding, useOnboarding } from "./api";

/** The plan in one line, as the invite email's plan card says it: "基础版 · 每月 4 小时音频". */
export function planLine(p: MyPlan | null): string | null {
  if (!p) return null;
  const l = p.limits;
  const h = l.hours === null ? t("音频时长不限") : l.hours_once ? t("一次性 {n} 小时音频", { n: l.hours }) : t("每月 {n} 小时音频", { n: l.hours });
  return `${l.name} · ${h}`;
}

/** 首页 of a new account's first show before it is set up (C3, new-user batch): "欢迎，Sam" and two ways in,
 *  the sample show or their own recording. `children` is the 建节目 form, shown once they pick their own. */
export function Welcome({ children }: { children: ReactNode }) {
  const ob = useOnboarding();
  const [st, setSt] = useState<AuthStatus | null>(null);
  const [plan, setPlan] = useState<MyPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    authApi.status().then(setSt, () => undefined);
    plansApi.mine().then(setPlan, () => undefined);
  }, []);
  if (ob === undefined) return null;
  if (!ob || ob.welcomed || ob.collab) return <>{children}</>;
  const later = () => onboardingApi.flags({ welcomed: true }).then(setOnboarding, (e) => setErr((e as Error).message));
  const sample = async () => {
    setBusy(true);
    try {
      await openSample(lang);
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  };
  const line = planLine(plan);
  return (
    <section className="welcome" data-testid="welcome">
      <h1>{st?.name ? t("欢迎，{name}", { name: st.name }) : t("欢迎来到 LACUNA")}</h1>
      <p className="welcome-lead">{t("LACUNA 先替你剪第一刀：口误、重复、过长的停顿和跑题。你来听、来决定，然后加音乐、导出。")}</p>
      <div className="welcome-ways">
        <article className="card welcome-way">
          <span className="chip chip-ok">{t("不占用你的额度")}</span>
          <h2>{t("先用示例集试一遍")}</h2>
          <p className="muted">{t("一集几分钟的双人对话，已经剪好第一刀。约 5 分钟走完全流程。")}</p>
          <button type="button" className="btn btn-primary" onClick={() => void sample()} disabled={busy} data-testid="welcome-sample">
            {ob.sample ? t("回到示例节目") : t("开始试用示例")}
          </button>
        </article>
        <article className="card welcome-way">
          <h2>{t("直接导入我的录音")}</h2>
          <p className="muted">{t("先建一个节目。需要每位主持人单独一条录音（Riverside、Zencastr、Zoom 分轨都可以）。")}</p>
          <button type="button" className="btn btn-outline" onClick={() => void later()} data-testid="welcome-own">
            {t("建我的节目")}
          </button>
        </article>
      </div>
      <p className="welcome-foot">
        {line && <span className="muted small" data-testid="welcome-plan">{t("你的套餐：{plan}", { plan: line })}</span>}
        <span className="grow" />
        <button type="button" className="btn btn-ghost btn-small" onClick={() => void later()} data-testid="welcome-later">
          {t("以后再说")}
        </button>
      </p>
      {err && <p className="error">{err}</p>}
    </section>
  );
}

/** Accounts from before names (Leon, Pei): asked once, on 首页 (Q12). */
export function NameAsk() {
  const [st, setSt] = useState<AuthStatus | null>(null);
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    authApi.status().then(setSt, () => undefined);
  }, []);
  if (!st?.email || st.name) return null;
  const save = (e: React.FormEvent) => {
    e.preventDefault();
    authApi.setName(name).then(
      (r) => setSt({ ...st, name: r.name }),
      (x) => setErr((x as Error).message),
    );
  };
  return (
    <form className="card name-ask" onSubmit={save} data-testid="name-ask">
      <label>
        <strong>{t("怎么称呼你？")}</strong>
        <span className="muted small">{t("邀请邮件和多人剪辑里会显示这个名字，以后可以在设置 → 账号里改。")}</span>
      </label>
      <div className="row gap8">
        <input value={name} onChange={(e) => setName(e.target.value)} maxLength={40} required aria-label={t("你的名字")} />
        <button type="submit" className="btn btn-primary" disabled={!name.trim()}>
          {t("保存")}
        </button>
      </div>
      {err && <p className="error">{err}</p>}
    </form>
  );
}
