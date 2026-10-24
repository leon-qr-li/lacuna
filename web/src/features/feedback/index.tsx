import { createRoot } from "react-dom/client";
import { t } from "../../i18n";
import type { Feature } from "../registry";
import { FeedbackHost } from "./Panel";
import { MyFeedback } from "./MyFeedback";
import { FeedbackButton } from "./parts";
import { AllFeedback } from "./AllFeedback";
import { useStaff } from "./unread";
import { openFeedback } from "./bus";
import { installTrail } from "./trail";
import "./feedback.css";

// 用户反馈 (decision 2026-10-24-user-feedback): the 反馈 button in the top bar, its panel (one copy for the
// whole app, mounted on <body> so it stays open across screens), 我的反馈 at #/feedback (the reply email's link)
// and, for the site owner until the admin exists, everyone's feedback at #/feedback-all.
installTrail();
if (typeof document !== "undefined") {
  const host = document.createElement("div");
  host.className = "fb-root";
  document.body.appendChild(host);
  createRoot(host).render(<FeedbackHost />);
}

function MinePage() {
  const staff = useStaff();
  return (
    <main className="fb-page">
      <div className="row fb-page-head">
        <h1>{t("我的反馈")}</h1>
        <span className="grow" />
        {staff && (
          <a className="btn btn-outline" href="#/feedback-all" data-testid="feedback-all-link">
            {t("全部反馈（临时）")}
          </a>
        )}
        <button type="button" className="btn btn-primary" onClick={() => openFeedback()}>
          {t("写新反馈")}
        </button>
      </div>
      <MyFeedback onWrite={() => openFeedback()} />
    </main>
  );
}

function AllPage() {
  return (
    <main className="fb-page fb-page-wide">
      <div className="row fb-page-head">
        <h1>{t("全部反馈（临时）")}</h1>
      </div>
      <AllFeedback />
    </main>
  );
}

export const feature: Feature = {
  pages: [
    { path: "feedback", title: t("我的反馈"), render: () => <MinePage /> },
    { path: "feedback-all", title: t("全部反馈（临时）"), render: () => <AllPage /> },
  ],
  nav: [{ order: 28, path: "feedback", render: () => <FeedbackButton />, on: ["home", "episode", "page"] }],
};
