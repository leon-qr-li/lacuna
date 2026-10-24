import { t } from "../../i18n";
import { uploadProgress, uploading, useDraft, useFormShown } from "./draft";

/** Top bar, while tracks upload and the import form isn't on screen: how far they are, a link back to it. */
export function UploadBadge() {
  const d = useDraft();
  const shown = useFormShown();
  const n = d ? uploading().length : 0;
  if (!n || shown) return null;
  const pct = Math.round(uploadProgress() * 100);
  return (
    <a className="upload-badge" href="#/" data-testid="upload-badge" title={t("回到导入表单")}>
      <span className="upload-badge-bar" aria-hidden>
        <span style={{ width: `${Math.max(pct, 3)}%` }} />
      </span>
      {t("正在上传 {id} · {pct}%", { id: d!.id, pct })}
    </a>
  );
}
