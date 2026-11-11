import { useState } from "react";
import { t } from "../../i18n";
import { confirmDialog, noticeDialog } from "../dialog/Dialog";
import { BusyLabel } from "../loading/Loading";
import { namingApi, type Naming } from "./api";

const SHOW = 6;

/** 「把已有的 N 集也按这个格式改名」: asks first with the titles before and after; only then renames (and saves the format). */
export function RenameExisting({ album, naming, count, onDone, asking }: {
  album: string;
  naming: Naming | null;
  count: number;
  onDone: () => void;
  /** a question is open: the album dialog leaves Esc to it */
  asking: (on: boolean) => void;
}) {
  const [busy, setBusy] = useState(false);
  if (!naming || !count) return null;
  const go = async () => {
    setBusy(true);
    try {
      const { renames } = await namingApi.preview(album, naming);
      asking(true);
      if (!renames.length) {
        await noticeDialog(t("专辑里的剧集已经都是这个格式了。"));
        return;
      }
      const lines = renames.slice(0, SHOW).map((r) => `${r.before} → ${r.after}`);
      if (renames.length > SHOW) lines.push(t("…还有 {n} 集", { n: renames.length - SHOW }));
      const ok = await confirmDialog({
        title: t("把 {n} 集改成新格式？", { n: renames.length }),
        message: `${lines.join("\n")}\n\n${t("只改剧集的标题，剪辑、音频和发布资料都不动；以后换了格式可以再改一次。")}`,
        confirmLabel: t("改名"),
      });
      if (!ok) return;
      await namingApi.set(album, naming);
      const { renamed } = await namingApi.apply(album);
      await noticeDialog(t("已改名 {n} 集。", { n: renamed.length }));
      onDone();
    } catch (e) {
      await noticeDialog((e as Error).message);
    } finally {
      asking(false);
      setBusy(false);
    }
  };
  return (
    <div className="nm-rename">
      <button type="button" className="btn btn-outline btn-small" disabled={busy} onClick={() => void go()} data-testid="naming-rename">
        <BusyLabel busy={busy} label={t("把已有的 {n} 集也按这个格式改名…", { n: count })} />
      </button>
      <span className="small muted">{t("不点就只管以后导入的新剧集。")}</span>
    </div>
  );
}
