// 用户动态 (decision 2026-10-31-admin-user-activity): the full page (/activity?u=<email>) and the summary in the
// user drawer. Reads only; the server records each look in the audit log.
import { useEffect, useMemo, useState } from "react";
import { get } from "../api";
import { demoData } from "../demo";
import { locale, t } from "../i18n";
import { Card, Chips, Empty, Loading, PageHead, isDemo } from "../ui";
import "./activity.css";
import { type ActRow, type ActWindow, type Filter, type Item, clock, days, detail, keep, sessions, tone, week, what } from "./logic";

const url = (email: string, before?: number) =>
  `/api/admin/users/${encodeURIComponent(email)}/activity?days=7${before ? `&before=${before}` : ""}`;

const load = (u: string) => (isDemo() ? Promise.resolve(demoData(u) as ActWindow) : get<ActWindow>(u));

/** Open the full page from anywhere (the shell follows popstate). */
export function openActivity(email: string) {
  history.pushState(null, "", `/activity?u=${encodeURIComponent(email)}`);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function ActivityPage() {
  const email = new URLSearchParams(location.search).get("u") || "";
  const [win, setWin] = useState<ActWindow | null>(null);
  const [rows, setRows] = useState<ActRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  useEffect(() => {
    if (!email) return;
    load(url(email)).then(
      (w) => {
        setWin(w);
        setRows(w.rows);
      },
      (e: Error) => setError(e.message),
    );
  }, [email]);
  const more = async () => {
    if (!win) return;
    setBusy(true);
    try {
      const w = await load(url(email, win.start));
      setWin(w);
      setRows((r) => [...r, ...w.rows]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const list = useMemo(() => days(sessions(rows.filter((r) => keep(filter, r.ev)))), [rows, filter]);
  if (!email) return <Loading error={t("没有指定用户")} />;
  const name = win?.user.name || email;
  return (
    <>
      <PageHead
        title={t("{who} 的动态", { who: name })}
        sub={
          <>
            <a
              className="a-act-back"
              href={`/users?u=${encodeURIComponent(email)}`}
              onClick={(e) => {
                e.preventDefault();
                history.pushState(null, "", `/users?u=${encodeURIComponent(email)}`);
                window.dispatchEvent(new PopStateEvent("popstate"));
              }}
            >
              {t("← 用户")}
            </a>{" "}
            · {email}
          </>
        }
      />
      <div className="a-filters">
        <Chips<Filter>
          value={filter}
          onChange={setFilter}
          items={[
            { id: "all", label: t("全部") },
            { id: "edit", label: t("剪辑") },
            { id: "ai", label: t("AI") },
            { id: "io", label: t("导入导出") },
            { id: "account", label: t("账号与节目") },
            { id: "failed", label: t("只看失败") },
          ]}
        />
      </div>
      {!win ? (
        <Loading error={error} />
      ) : (
        <div className="a-act" data-testid="activity">
          {list.length ? (
            list.map((d) => (
              <section key={d.key}>
                <h3 className="a-act-day">{d.label}</h3>
                {d.sessions.map((s) => (
                  <Card key={s.end} pad={false} className="a-act-ses">
                    <div className="a-act-sh">
                      <b>
                        {clock(s.start)} – {clock(s.end)}
                      </b>
                      <span>{t("{n} 分钟", { n: Math.max(1, Math.round((s.end - s.start) / 60)) })}</span>
                      {s.shows.map((x) => (
                        <span key={x} className="show">
                          {x}
                        </span>
                      ))}
                      <span>{t("{n} 个操作", { n: s.n })}</span>
                    </div>
                    {s.items.map((it, i) => (
                      <Line key={i} it={it} />
                    ))}
                  </Card>
                ))}
              </section>
            ))
          ) : (
            <Card>
              <Empty icon="log" title={filter === "all" ? t("这段时间没有动态") : t("这段时间没有符合的动态")} />
            </Card>
          )}
          {error && <p className="a-error">{error}</p>}
          <div className="a-act-more">
            {win.older ? (
              <button type="button" className="a-btn" onClick={more} disabled={busy} data-testid="activity-older">
                {t("加载更早的动态")}
              </button>
            ) : (
              <span className="a-muted small">{t("没有更早的动态了")}</span>
            )}
          </div>
          <p className="a-muted small">{t("只显示做了什么，不显示内容。你的这次查看已记入操作日志。")}</p>
        </div>
      )}
    </>
  );
}

function Line({ it }: { it: Item }) {
  const [open, setOpen] = useState(false);
  const n = it.rows.length;
  const d = detail(it);
  const ep = it.title || it.ep;
  return (
    <div className={`a-act-row ${tone(it)}`} data-testid="activity-row">
      <time>{clock(it.ts)}</time>
      <span className="dot" />
      <div className="what">
        {what(it.ev)}
        {it.failed && <span className="a-pill bad">{t("没成功")}</span>}
        {ep && <span className="ep">{ep}</span>}
        {n > 1 && (
          <button type="button" className="x" aria-expanded={open} onClick={() => setOpen(!open)}>
            ×{n}
          </button>
        )}
        {d && <span className="d">{d}</span>}
        {open && (
          <ul className="each">
            {it.rows.map((r, i) => (
              <li key={i}>
                <time>{clock(r.ts)}</time> {detail({ ...it, rows: [r] }) || what(r.ev)}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/** The drawer's 最近动态: the last session, the last 7 days, the latest five things, and the way to the page. */
export function DrawerActivity({ email, rows }: { email: string; rows: ActRow[] }) {
  const ses = sessions(rows);
  const last = ses[0];
  const bars = week(rows);
  const top = Math.max(1, ...bars.map((b) => b.n));
  const items = ses.flatMap((s) => s.items).slice(0, 5);
  return (
    <section className="a-act-drawer" data-testid="drawer-activity">
      <h4 className="a-row">
        <span className="a-grow">{t("最近动态")}</span>
        <button type="button" className="a-btn ghost sm" onClick={() => openActivity(email)} data-testid="open-activity">
          {t("查看全部动态 →")}
        </button>
      </h4>
      {!last ? (
        <p className="a-muted small">{t("还没有活动")}</p>
      ) : (
        <>
          <div className="a-act-last">
            <span className="a-muted small">{t("最近一次使用")}</span>
            <b>
              {new Date(last.end * 1000).toLocaleDateString(locale, { month: "numeric", day: "numeric" })} {clock(last.start)} – {clock(last.end)} · {t("{n} 个操作", { n: last.n })}
            </b>
            {last.items.some((i) => i.title || i.ep) && (
              <span className="a-muted small">{[...new Set(last.items.map((i) => i.title || i.ep).filter(Boolean))].slice(0, 3).join(" · ")}</span>
            )}
          </div>
          <div className="a-act-week" aria-label={t("最近 7 天")}>
            {bars.map((b, i) => (
              <div key={i} title={t("{n} 个操作", { n: b.n })}>
                <i>
                  <b style={{ height: `${(b.n / top) * 100}%` }} />
                </i>
                {b.label}
              </div>
            ))}
          </div>
          <div className="a-act-mini">
            {items.map((it, i) => (
              <div key={i} className={`a-act-row ${tone(it)}`}>
                <time>{clock(it.ts)}</time>
                <span className="dot" />
                <div className="what">
                  {what(it.ev)}
                  {it.failed && <span className="a-pill bad">{t("没成功")}</span>}
                  {(it.title || it.ep) && <span className="ep">{it.title || it.ep}</span>}
                  {it.rows.length > 1 && <span className="x">×{it.rows.length}</span>}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
