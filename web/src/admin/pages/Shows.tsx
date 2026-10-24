// 节目与剧集: every show (members, episodes, disk use, last activity), the episodes that are stuck (import failed,
// or 14 days without an export), and the 自动发布 votes from show settings.
import { useState } from "react";
import type { PageProps } from "../Shell";
import { t } from "../i18n";
import { PLATFORM, eventName } from "../labels";
import type { ShowsData } from "../types";
import { Card, Empty, HBar, Loading, PageHead, Pill, Tabs, ago, fmtBytes, fmtDate, useData } from "../ui";
import { OpenShow } from "./Users";

type Tab = "shows" | "stuck" | "votes";

export function ShowsPage(_: PageProps) {
  const [tab, setTab] = useState<Tab>("shows");
  const { data, error } = useData<ShowsData>("/api/admin/shows");
  const real = data ? data.shows.filter((s) => !s.sample) : [];
  return (
    <>
      <PageHead title={t("节目与剧集")} sub={data ? t("{n} 个节目 · {e} 集", { n: real.length, e: real.reduce((a, s) => a + s.episodes, 0) }) : undefined} />
      {!data ? (
        <Loading error={error} />
      ) : (
        <>
          <Tabs<Tab>
            value={tab}
            onChange={setTab}
            items={[
              { id: "shows", label: t("节目"), n: real.length },
              { id: "stuck", label: t("卡住的剧集"), n: data.stuck.length },
              { id: "votes", label: t("自动发布投票") },
            ]}
          />
          {tab === "shows" && <Shows data={data} />}
          {tab === "stuck" && <Stuck data={data} />}
          {tab === "votes" && <Votes data={data} />}
        </>
      )}
    </>
  );
}

function Shows({ data }: { data: ShowsData }) {
  const [samples, setSamples] = useState(false);
  const rows = data.shows.filter((s) => samples || !s.sample);
  return (
    <>
      <div className="a-filters">
        <label className="a-row small">
          <input type="checkbox" checked={samples} onChange={(e) => setSamples(e.target.checked)} />
          {t("也显示示例节目")}
        </label>
        <span className="spacer" />
        <span className="a-muted small">{data.sizes_at ? t("占用空间统计于 {t}", { t: ago(data.sizes_at) }) : t("占用空间正在统计…")}</span>
      </div>
      {!rows.length ? (
        <Card>
          <Empty icon="mic" title={t("还没有节目")} />
        </Card>
      ) : (
        <Card pad={false}>
          <div className="a-tw">
            <table className="a-t a-t-cards">
              <thead>
                <tr>
                  <th>{t("节目")}</th>
                  <th>{t("创建人")}</th>
                  <th className="n">{t("成员")}</th>
                  <th className="n">{t("剧集")}</th>
                  <th className="n">{t("占用空间")}</th>
                  <th>{t("创建")}</th>
                  <th>{t("最近活动")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((s) => (
                  <tr key={s.id} data-testid="show-row">
                    <td>
                      <b className="a-w5">{s.name}</b>
                      {s.sample && <Pill>{t("示例")}</Pill>}
                      {s.archived && <Pill>{t("已归档")}</Pill>}
                      {s.language && <span className="a-muted small"> · {s.language === "en" ? t("英文节目") : t("中文节目")}</span>}
                    </td>
                    <td className="a-muted" data-label={t("创建人")}>
                      {s.creator || "—"}
                    </td>
                    <td className="n" data-label={t("成员")}>
                      {s.members}
                    </td>
                    <td className="n" data-label={t("剧集")}>
                      {s.episodes}
                    </td>
                    <td className="n" data-label={t("占用空间")}>
                      {fmtBytes(s.size)}
                    </td>
                    <td className="a-muted" data-label={t("创建")}>
                      {fmtDate(s.created)}
                    </td>
                    <td className="a-muted" data-label={t("最近活动")}>
                      {ago(s.last)}
                    </td>
                    <td>
                      <OpenShow sid={s.id} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </>
  );
}

function Stuck({ data }: { data: ShowsData }) {
  if (!data.stuck.length)
    return (
      <Card>
        <Empty icon="mic" title={t("没有卡住的剧集")} sub={t("导入失败、或者 14 天没导出也没人动的剧集会出现在这里。")} />
      </Card>
    );
  return (
    <Card pad={false}>
      <div className="a-tw">
        <table className="a-t a-t-cards">
          <thead>
            <tr>
              <th>{t("节目")}</th>
              <th>{t("剧集")}</th>
              <th>{t("为什么")}</th>
              <th>{t("最后一步")}</th>
              <th>{t("多久没动")}</th>
              <th>{t("最后动它的人")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data.stuck.map((r) => (
              <tr key={`${r.sid}/${r.ep}`} data-testid="stuck-row">
                <td>{r.show}</td>
                <td data-label={t("剧集")}>{r.ep}</td>
                <td data-label={t("为什么")}>{r.why === "failed" ? <Pill tone="bad">{t("导入失败")}</Pill> : <Pill tone="warn">{t("14 天没动")}</Pill>}</td>
                <td className="a-muted" data-label={t("最后一步")}>
                  {eventName(r.ev)}
                </td>
                <td data-label={t("多久没动")}>{ago(r.last)}</td>
                <td className="a-muted" data-label={t("最后动它的人")}>
                  {r.who || "—"}
                </td>
                <td>
                  <OpenShow sid={r.sid} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function Votes({ data }: { data: ShowsData }) {
  const max = Math.max(1, ...Object.values(data.votes));
  return (
    <div className="a-grid g-21">
      <Card title={t("想要自动发布到哪")} sub={t("{n} 个节目勾选过", { n: data.voters })}>
        {data.voters ? (
          <div className="a-hbars">
            {Object.keys(PLATFORM).map((p) => (
              <HBar key={p} label={PLATFORM[p]} value={data.votes[p] ?? 0} max={max} text={t("{n} 个节目", { n: data.votes[p] ?? 0 })} />
            ))}
          </div>
        ) : (
          <Empty icon="chart" title={t("还没有节目勾选")} />
        )}
      </Card>
      <Card title={t("说明")}>
        <p className="a-muted">{t("来自节目设置里的「自动发布 · 即将推出」卡片。一个节目可以勾多个平台。点「告诉我们」写的反馈在「反馈 → 自动发布」里。")}</p>
      </Card>
    </div>
  );
}
