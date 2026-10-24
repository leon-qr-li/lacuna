import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { t } from "../../i18n";
import type { Feature } from "../registry";
import "./site-notice.css";

// 站内公告 and 维护模式 (decision 2026-10-24-admin-site): set in the admin, shown here as one bar at the top of every
// screen (lacuna_app/routes/upkeep.py). A notice closed with × stays closed until a new one is posted.
interface SiteNotice {
  notice: { text: string; at: number } | null;
  maintenance: boolean;
}
const CLOSED = "lacuna.notice.closed";

function NoticeBar() {
  const [n, setN] = useState<SiteNotice | null>(null);
  const [closed, setClosed] = useState<string | null>(() => {
    try {
      return localStorage.getItem(CLOSED);
    } catch {
      return null;
    }
  });
  useEffect(() => {
    // a plain fetch: before sign-in this answers 401, which must not bring up the sign-in screen (api.ts failure)
    const load = () =>
      fetch("/api/site/notice")
        .then((r) => (r.ok ? (r.json() as Promise<SiteNotice>) : null))
        .then((x) => x && setN(x), () => undefined);
    load();
    // also on coming back to the tab (and right after signing in, which happens without a page load)
    const id = window.setInterval(load, 5 * 60_000);
    window.addEventListener("focus", load);
    window.addEventListener("hashchange", load);
    return () => {
      window.clearInterval(id);
      window.removeEventListener("focus", load);
      window.removeEventListener("hashchange", load);
    };
  }, []);
  if (!n) return null;
  const key = n.notice ? String(n.notice.at) : null;
  const showNotice = n.notice && key !== closed;
  if (!n.maintenance && !showNotice) return null;
  return (
    <div className="site-notice" role="status" data-testid="site-notice">
      {n.maintenance && <p className="site-notice-maint">{t("LACUNA 正在维护：暂时不能上传和导入新的剧集，其他功能照常。几分钟后再试。")}</p>}
      {showNotice && (
        <p className="site-notice-text">
          <span>{n.notice!.text}</span>
          <button
            type="button"
            aria-label={t("关闭公告")}
            onClick={() => {
              setClosed(key);
              try {
                localStorage.setItem(CLOSED, key ?? "");
              } catch {
                /* private mode: closed for this visit */
              }
            }}
          >
            ×
          </button>
        </p>
      )}
    </div>
  );
}

if (typeof document !== "undefined") {
  const host = document.createElement("div");
  host.className = "site-notice-root";
  document.body.appendChild(host);
  createRoot(host).render(<NoticeBar />);
}

export const feature: Feature = {};
