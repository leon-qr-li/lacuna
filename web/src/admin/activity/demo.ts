// 演示数据 for 用户动态: two days of one made-up account's work, with a failed import and a merged run of cuts.
import type { ActRow, ActWindow } from "./logic";

const M = 60;
const H = 3600;

export function demoActivity(email: string, before: number | null): ActWindow {
  const now = Date.now() / 1000;
  const show = "周末电影院"; // i18n-ignore
  const ep12 = "第 12 期：重看《花样年华》"; // i18n-ignore
  const ep13 = "第 13 期"; // i18n-ignore
  const ep11 = "第 11 期"; // i18n-ignore
  const r = (ago: number, ev: string, ep: string | null, title: string | null, props: Record<string, unknown> = {}): ActRow => ({
    ts: now - ago,
    ev,
    sid: ep ? "s0" : null,
    show: ep ? show : null,
    ep,
    title,
    props,
  });
  const rows: ActRow[] = before
    ? []
    : [
        r(1 * M, "export.done", "EP12", ep12, { length_s: 3494, seconds: 71, formats: 2 }),
        r(2 * M, "export.start", "EP12", ep12),
        r(14 * M, "levels.auto", "EP12", ep12),
        r(22 * M, "chat.approve", "EP12", ep12),
        r(23 * M, "chat.message", "EP12", ep12),
        r(25 * M, "chat.message", "EP12", ep12),
        ...Array.from({ length: 14 }, (_, i) => r(30 * M + i * 50, "edit.manual", "EP12", ep12, { seconds: 1.5 + (i % 4) })),
        r(43 * M, "edit.manual.failed", "EP12", ep12, { status: 409 }),
        ...Array.from({ length: 31 }, (_, i) => r(45 * M + i * 20, "review.decide", "EP12", ep12, { action: i % 8 === 0 ? "restore" : "keep" })),
        r(57 * M, "user.login", null, null),
        r(5 * H, "import.error", "EP13", ep13, { failed_step: "asr_L", audio_s: 3840 }),
        r(5 * H + 21 * M, "import.start", "EP13", ep13),
        r(5 * H + 23 * M, "user.login", null, null),
        r(26 * H, "poster.choose", "EP11", ep11),
        r(26 * H + 9 * M, "poster.generate", "EP11", ep11),
        r(26 * H + 12 * M, "poster.generate", "EP11", ep11),
        r(26 * H + 14 * M, "poster.generate", "EP11", ep11),
        r(26 * H + 18 * M, "publish.generate", "EP11", ep11),
        r(26 * H + 25 * M, "user.login", null, null),
      ];
  return {
    user: { email, name: email.split("@")[0], role: "member", plan: "basic" },
    rows,
    start: (before ?? now + 1) - 7 * 86400,
    end: before ?? now + 1,
    older: !before,
  };
}
