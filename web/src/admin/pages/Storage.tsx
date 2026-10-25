// 存储与保留 (on 系统健康): old episodes' audio in cloud storage (lacuna_app/cold.py) and how long audio is kept
// (lacuna_app/retention.py). Raw-track deletion is off during the beta; only the site owner changes it.
import { useState } from "react";
import { api } from "../api";
import { t } from "../i18n";
import type { StorageData } from "../types";
import { Card, Pill, Switch, act, fmtBytes } from "../ui";

export function StorageCard({ data, owner }: { data: StorageData; owner: boolean }) {
  const [s, setS] = useState(data);
  const change = async (k: keyof StorageData["retention"], v: boolean) => {
    const out = await act(() => api<StorageData>("PUT", "/api/admin/storage/retention", { [k]: v }), t("保留规则已保存"));
    if (out) setS(out);
  };
  const rows: [keyof StorageData["retention"], string, string][] = [
    ["old_exports", t("导出只留最新的"), t("同一集有了新导出 7 天后，删掉旧的音频文件（导出记录保留）。")],
    ["raw_tracks", t("原始音轨保留 12 个月"), t("一集 12 个月没打开就删原始分轨，提前 30 天邮件提醒创建节目的人；逐字稿、剪辑记录、节目介绍和最新导出永久保留。beta 期间关着。")],
  ];
  return (
    <Card
      title={t("存储与保留")}
      right={s.cold.on ? <Pill tone="ok">{t("云存储已接通")}</Pill> : <Pill tone="warn">{t("云存储未接通")}</Pill>}
      sub={t("{d} 天没打开的剧集，音频搬到云存储；打开时自动取回（10–30 秒）。", { d: s.cold.after_days })}
    >
      <p className="a-muted small" data-testid="storage-cold">
        {s.cold.on ? t("现在放在云存储的音频：{b}", { b: fmtBytes(s.cold.bytes) }) : t("服务器还没有云存储的密钥，音频都留在服务器上。")}
      </p>
      <div className="a-stack">
        {rows.map(([k, label, sub]) => (
          <div key={k} className="a-row wrap">
            <Switch on={s.retention[k]} onChange={(v) => void change(k, v)} label={label} disabled={!owner} testid={`retention-${k}`} />
            <b>{label}</b>
            <span className="a-muted small">{sub}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}
