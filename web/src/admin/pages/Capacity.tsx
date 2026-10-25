// 容量 (admin home): is the server big enough? Disk (and days until full), the import queue, this month's audio
// hours against what the server can process, memory, Cloudflare Access seats (lacuna_app/capacity.py). A measure
// past a threshold also mails the owner (once a day; again at once if it gets worse) and shows in the 8:00 digest.
import { t } from "../i18n";
import type { CapacityMeasure } from "../types";
import { Card, Pill } from "../ui";

const NAMES: Record<CapacityMeasure["key"], () => string> = {
  disk: () => t("数据盘"),
  queue: () => t("导入排队"),
  hours: () => t("本月音频"),
  memory: () => t("内存"),
  people: () => t("Access 名额"),
};
const GRADE = { ok: ["ok", () => t("正常")], warn: ["warn", () => t("注意")], act: ["bad", () => t("该行动")], urgent: ["bad", () => t("紧急")] } as const;

export function CapacityCard({ measures }: { measures: CapacityMeasure[] }) {
  return (
    <Card title={t("容量")} sub={t("超过阈值立刻发邮件，每天早上的汇总里也有")} testid="capacity">
      <div className="a-stack">
        {measures.map((m) => {
          const [tone, label] = GRADE[m.level];
          return (
            <div key={m.key} className="a-row wrap" data-testid={`capacity-${m.key}`}>
              <b style={{ minWidth: "7em" }}>{NAMES[m.key]()}</b>
              <Pill tone={tone}>{label()}</Pill>
              <span className="a-grow">{m.line}</span>
              {m.level !== "ok" && <span className="a-muted small" style={{ flexBasis: "100%" }}>{m.advice}</span>}
            </div>
          );
        })}
      </div>
    </Card>
  );
}
