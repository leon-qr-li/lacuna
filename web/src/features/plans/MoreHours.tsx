import { useEffect, useState } from "react";
import { fmtDateTime, t } from "../../i18n";
import { BusyLabel } from "../loading/Loading";
import { plansApi, type HourRequest } from "./api";

const STATUS: Record<string, () => string> = {
  new: () => t("等 LACUNA 处理"),
  approved: () => t("已批准"),
  declined: () => t("没批"),
};

/** 「想要更多时长」 (decision 2026-10-24-admin-site): ask the owner for more hours this month. The owner approves or
 *  declines it in the admin (never automatic) and the answer also comes by email. */
export function MoreHours() {
  const [reqs, setReqs] = useState<HourRequest[] | null>(null);
  const [open, setOpen] = useState(false);
  const [hours, setHours] = useState("2");
  const [reason, setReason] = useState("");
  const [pay, setPay] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    plansApi.hours().then((r) => setReqs(r.requests), () => setReqs([]));
  }, []);
  if (!reqs) return null;
  const waiting = reqs.some((r) => r.status === "new");
  const send = async () => {
    setBusy(true);
    setErr(null);
    try {
      setReqs((await plansApi.askHours(Number(hours), reason, pay)).requests);
      setOpen(false);
      setReason("");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="plan-more" data-testid="more-hours">
      {!open && (
        <button type="button" className="btn btn-outline btn-small" disabled={waiting} onClick={() => setOpen(true)} data-testid="more-hours-open">
          {waiting ? t("申请已发出，等 LACUNA 处理") : t("想要更多时长")}
        </button>
      )}
      {open && (
        <div className="plan-more-form">
          <label className="small">
            {t("这个月想多要几小时")}
            <input type="number" min={0.5} max={50} step={0.5} value={hours} onChange={(e) => setHours(e.target.value)} data-testid="more-hours-n" />
          </label>
          <label className="small">
            {t("说说为什么（可以不写）")}
            <textarea rows={2} maxLength={1000} value={reason} onChange={(e) => setReason(e.target.value)} data-testid="more-hours-reason" />
          </label>
          <label className="small row gap8">
            <input type="checkbox" checked={pay} onChange={(e) => setPay(e.target.checked)} />
            {t("以后正式收费时，我愿意为更多时长付费")}
          </label>
          {err && <p className="error small">{err}</p>}
          <div className="row gap8">
            <button type="button" className="btn btn-primary btn-small" disabled={busy || !(Number(hours) > 0)} onClick={send} data-testid="more-hours-send">
              <BusyLabel busy={busy} label={t("发出申请")} />
            </button>
            <button type="button" className="btn btn-ghost btn-small" onClick={() => setOpen(false)}>
              {t("取消")}
            </button>
          </div>
          <p className="muted small">{t("每一条都有人亲自看，结果会发邮件告诉你。")}</p>
        </div>
      )}
      {reqs.length > 0 && (
        <ul className="plan-more-list">
          {reqs.slice(0, 3).map((r) => (
            <li key={r.id}>
              <span>{t("{n} 小时", { n: r.status === "approved" && r.granted ? r.granted : r.hours })}</span>
              <span className="muted small">{fmtDateTime(r.created * 1000)}</span>
              <span className={`plan-more-st st-${r.status}`}>{(STATUS[r.status] ?? (() => r.status))()}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
