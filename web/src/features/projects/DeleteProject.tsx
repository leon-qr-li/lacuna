import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { t } from "../../i18n";
import { BusyLabel } from "../loading/Loading";
import { spacesApi, type MySpace } from "../spaces/api";
import { setProjects } from "./api";

/**
 * 永久删除 an archived project: type its name to confirm (decision projects-archive-delete). Not
 * confirmDialog: that one has no text box. Rendered into <body> like the other dialogs.
 */
export function DeleteProjectDialog({ p, here, onClose }: { p: MySpace; here: boolean; onClose: () => void }) {
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    input.current?.focus();
    const key = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [onClose]);
  const ok = typed.trim() === p.name;
  const go = async () => {
    setBusy(true);
    setErr(null);
    try {
      const sp = await spacesApi.remove(p.id, typed);
      if (here) {
        // everything on screen belonged to it: start fresh in the project you land in
        window.location.reload();
        return;
      }
      setProjects(sp);
      onClose();
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  };
  return createPortal(
    <div className="dlg-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <form
        className="dlg prj-dlg"
        role="dialog"
        aria-modal="true"
        aria-labelledby="prj-del-title"
        data-testid="project-delete-dialog"
        onSubmit={(e) => {
          e.preventDefault();
          if (ok && !busy) void go();
        }}
      >
        <h2 id="prj-del-title">{t("永久删除「{name}」", { name: p.name })}</h2>
        <p>
          {t("这个项目里的所有剧集、专辑、素材、导出文件和协作者都会被删除，不能恢复。学到的规则和剪辑力度是你自己的，会留下。")}
        </p>
        <label className="prj-field">
          <span className="prj-label">{t("输入项目名称「{name}」确认", { name: p.name })}</span>
          <input ref={input} value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" data-testid="project-delete-name" />
        </label>
        {err && <p className="error small">{err}</p>}
        <div className="dlg-actions">
          <button type="button" className="btn btn-outline" onClick={onClose}>
            {t("取消")}
          </button>
          <button type="submit" className="btn btn-danger" disabled={!ok || busy} data-testid="project-delete-confirm">
            <BusyLabel busy={busy} label={t("永久删除")} />
          </button>
        </div>
      </form>
    </div>,
    document.body,
  );
}
