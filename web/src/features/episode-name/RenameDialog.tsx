// 给这一集改名: an in-app dialog with one text field (the browser's prompt is not allowed, CLAUDE.md).
// Imperative like confirmDialog: `const v = await renameDialog(id)` resolves with the new name, or null.
import { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { t } from "../../i18n";
import "../dialog/dialog.css";
import "./episode-name.css";
import { nameApi, titleFor, type EpisodeName } from "./api";

function RenameBox({
  v,
  done,
}: {
  v: EpisodeName;
  done: (r: EpisodeName | null) => void;
}) {
  const [name, setName] = useState(v.name);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    input.current?.focus();
    input.current?.select();
  }, []);
  const save = async () => {
    if (busy) return;
    if (name.trim() === v.name) return done(null);
    setBusy(true);
    setErr("");
    try {
      done(await nameApi.set(v.id, name));
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  };
  const title = titleFor(v, name);
  return (
    <div
      className="dlg-backdrop"
      onMouseDown={(e) => e.target === e.currentTarget && done(null)}
      onKeyDown={(e) => {
        e.stopPropagation(); // the review shortcuts must not fire under the dialog
        if (e.key === "Escape") done(null);
      }}
    >
      <form
        className="dlg en-dlg"
        role="dialog"
        aria-modal="true"
        aria-labelledby="en-dlg-title"
        data-testid="rename-dialog"
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <h2 id="en-dlg-title">{t("给这一集改名")}</h2>
        <label className="en-field">
          {v.naming ? t("名称") : t("这一集叫什么")}
          <input
            ref={input}
            value={name}
            maxLength={200}
            onChange={(e) => setName(e.target.value)}
            placeholder={v.id}
            data-testid="rename-input"
          />
        </label>
        {v.naming && v.album ? (
          <p className="en-preview small" data-testid="rename-preview">
            {t("在专辑「{album}」里，会叫：{title}", {
              album: v.album.name,
              title,
            })}
          </p>
        ) : null}
        <p className="small muted">
          {name.trim()
            ? t("只改名字，剪辑、音频和发布资料的其他内容都不动。")
            : t("空着就先只用编号，以后再起。")}
        </p>
        {err && <p className="error small">{err}</p>}
        <div className="dlg-actions">
          <button
            type="button"
            className="btn btn-outline"
            onClick={() => done(null)}
          >
            {t("取消")}
          </button>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={busy}
            data-testid="rename-save"
          >
            {t("保存")}
          </button>
        </div>
      </form>
    </div>
  );
}

/** Ask for a new name and save it; resolves with the episode's new name, or null (cancelled / unchanged). */
export async function renameDialog(id: string): Promise<EpisodeName | null> {
  const v = await nameApi.get(id);
  const back = document.activeElement as HTMLElement | null;
  const host = document.createElement("div");
  host.className = "dlg-host";
  document.body.appendChild(host);
  const root = createRoot(host);
  return new Promise((resolve) => {
    let closed = false;
    const done = (r: EpisodeName | null) => {
      if (closed) return;
      closed = true;
      root.unmount();
      host.remove();
      back?.focus?.();
      resolve(r);
    };
    root.render(<RenameBox v={v} done={done} />);
  });
}
