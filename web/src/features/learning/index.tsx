import { useEffect, useState } from "react";
import { navCurrent, type Feature } from "../registry";
import { learningApi } from "./api";
import { LearningView } from "./LearningView";
import "./learning.css";
import { t } from "../../i18n";

function LearningLink() {
  const [pending, setPending] = useState<number | null>(null);
  useEffect(() => {
    learningApi
      .learning()
      .then((r) => setPending(r.pending))
      .catch(() => setPending(null));
  }, []);
  return (
    <a className="btn btn-outline row" href="#/learning" aria-current={navCurrent("learning")}>
      {t("学到的规则")}{pending ? t(" · {pending} 条待确认", { pending }) : ""}
    </a>
  );
}

export const feature: Feature = {
  pages: [{ path: "learning", title: t("学到的规则"), render: () => <LearningView /> }],
  nav: [{ order: 20, path: "learning", render: () => <LearningLink />, on: ["home", "episode", "page"] }],
};
