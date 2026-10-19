import { useEffect, useState } from "react";
import { t } from "../../i18n";

/** Top bar on the staging site: a clear "this is not the real site" mark. */
export function StagingBadge() {
  const [on, setOn] = useState(false);
  useEffect(() => {
    fetch("/api/staging")
      .then((r) => (r.ok ? r.json() : null))
      .then((info: { staging?: boolean } | null) => setOn(!!info?.staging), () => setOn(false));
  }, []);
  useEffect(() => {
    if (!on) return;
    const mark = t("Staging");
    const keep = () => {
      if (!document.title.startsWith(mark)) document.title = `${mark} · ${document.title}`;
    };
    keep();
    const obs = new MutationObserver(keep);
    const title = document.querySelector("title");
    if (title) obs.observe(title, { childList: true });
    return () => obs.disconnect();
  }, [on]);
  if (!on) return null;
  return (
    <span className="staging-badge" data-testid="staging-badge" title={t("这里是 staging：数据是正式站的一份复制，在这里怎么改都不影响正式站。")}>
      {t("Staging")}
    </span>
  );
}
