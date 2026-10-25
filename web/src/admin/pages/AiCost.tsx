// AI 省钱 (on 系统健康): site-wide AI switches (lacuna_app/ai_settings.py). The first cut through the Batch API
// halves its cost but makes imports wait longer, so it is off; only the site owner changes it.
import { useState } from "react";
import { api } from "../api";
import { t } from "../i18n";
import type { AiSettings } from "../types";
import { Card, Pill, Switch, act } from "../ui";

export function AiCostCard({ data, owner }: { data: AiSettings; owner: boolean }) {
  const [s, setS] = useState(data);
  const change = async (v: boolean) => {
    const out = await act(() => api<AiSettings>("PUT", "/api/admin/ai", { first_cut_batch: v }), t("AI 设置已保存"));
    if (out) setS(out);
  };
  const label = t("AI 第一刀走省钱模式");
  return (
    <Card
      title={t("AI 省钱")}
      right={s.first_cut_batch ? <Pill tone="warn">{t("省钱模式开着")}</Pill> : <Pill tone="ok">{t("正常速度")}</Pill>}
      sub={t("对话已用提示缓存，学习总结和曲名查询已用更便宜的模型；这些不影响速度，一直开着。")}
    >
      <div className="a-row wrap">
        <Switch on={s.first_cut_batch} onChange={(v) => void change(v)} label={label} disabled={!owner} testid="ai-first-cut-batch" />
        <b>{label}</b>
        <span className="a-muted small">{t("AI 第一刀的费用减半，但导入要多等，通常 10–30 分钟，高峰时可能几个小时。新用户的第一印象会打折，beta 期间建议关着。")}</span>
      </div>
    </Card>
  );
}
