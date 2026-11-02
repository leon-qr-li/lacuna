import { t } from "../../i18n";
import { noticeDialog } from "../dialog/Dialog";
import { renameDialog } from "./RenameDialog";
import type { EpisodeName } from "./api";

/** 「改名」 on an episode card (home page, album page). */
export function RenameButton({
  id,
  title,
  onRenamed,
}: {
  id: string;
  title: string;
  onRenamed: (v: EpisodeName) => void;
}) {
  return (
    <button
      type="button"
      className="btn btn-ghost btn-small"
      aria-label={t("给「{title}」改名", { title })}
      data-testid="episode-rename"
      onClick={(e) => {
        e.preventDefault();
        renameDialog(id).then(
          (v) => v && onRenamed(v),
          (err) => void noticeDialog((err as Error).message),
        );
      }}
    >
      {t("改名")}
    </button>
  );
}
