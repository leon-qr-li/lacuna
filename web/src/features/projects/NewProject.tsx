import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { t } from "../../i18n";
import { BusyLabel } from "../loading/Loading";
import { spacesApi } from "../spaces/api";
import { enterNew } from "./api";

/**
 * ＋ 新项目: just its name; the new project's 剧集 then asks for the language and hosts.
 * Rendered into <body>: opened from the top bar's project menu, a `position: fixed` backdrop inside the
 * blurred top bar would be placed against the bar (stuck at the top, half off-screen) instead of the window.
 */
export function NewProjectDialog({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    input.current?.focus();
    const key = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [onClose]);
  const create = async () => {
    setBusy(true);
    setErr(null);
    try {
      await spacesApi.create(name);
      enterNew();
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
        aria-labelledby="prj-new-title"
        data-testid="project-new-dialog"
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim() && !busy) void create();
        }}
      >
        <h2 id="prj-new-title">{t("新项目")}</h2>
        <p>{t("一档播客、一个客户、一个栏目都可以是一个项目。每个项目有自己的剧集、专辑和素材。")}</p>
        <label className="prj-field">
          <span className="prj-label">{t("项目名")}</span>
          <input ref={input} value={name} maxLength={80} onChange={(e) => setName(e.target.value)} placeholder={t("比如：周末电影院")} data-testid="project-name" />
        </label>
        {err && <p className="error small">{err}</p>}
        <div className="dlg-actions">
          <button type="button" className="btn btn-outline" onClick={onClose}>
            {t("取消")}
          </button>
          <button type="submit" className="btn btn-primary" disabled={!name.trim() || busy} data-testid="project-create">
            <BusyLabel busy={busy} label={t("建好项目")} />
          </button>
        </div>
      </form>
    </div>,
    document.body,
  );
}
