import { useEffect, useState } from "react";
import { t } from "../../i18n";
import type { CutLevel } from "../show/api";
import { habitsApi } from "./api";

const LEVELS: [CutLevel, string][] = [
  ["gentle", t("轻剪")],
  ["normal", t("正常")],
  ["firm", t("狠剪")],
];

/** 设置 → 剪辑习惯: the editor's 剪辑力度 (one for all their projects) and a way to 学到的规则. */
export function HabitsCard() {
  const [level, setLevel] = useState<CutLevel | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    habitsApi
      .get()
      .then((r) => setLevel(r.cut_level))
      .catch((e) => setErr(String((e as Error).message ?? e)));
  }, []);
  const pick = (v: CutLevel) => {
    const before = level;
    setLevel(v);
    setErr(null);
    habitsApi.setLevel(v).catch((e) => {
      setLevel(before);
      setErr(String((e as Error).message ?? e));
    });
  };
  return (
    <section className="card" aria-label={t("剪辑习惯")} data-testid="habits-card">
      <h2>{t("剪辑习惯")}</h2>
      <p className="muted small">{t("这里的设置用在你所有的节目上，包括别人邀请你协作的节目。")}</p>
      <div className="set-row">
        <div>
          <strong>{t("剪辑力度")}</strong>
          <p className="muted small">{t("每位主持人还可以在节目设置里调得更狠或更松。")}</p>
        </div>
        <div className="seg" role="radiogroup" aria-label={t("剪辑力度")}>
          {LEVELS.map(([v, label]) => (
            <button key={v} type="button" role="radio" aria-checked={level === v} className={level === v ? "is-on" : ""} disabled={!level} onClick={() => level !== v && pick(v)}>
              {label}
            </button>
          ))}
        </div>
      </div>
      <div className="set-row">
        <div>
          <strong>{t("学到的规则")}</strong>
          <p className="muted small">{t("你确认过的规则也跟着你走，用在你所有的节目上。")}</p>
        </div>
        <a className="btn btn-outline btn-small" href="#/learning/approved">
          {t("去看学到的规则")}
        </a>
      </div>
      {err && <p className="error small">{err}</p>}
    </section>
  );
}
