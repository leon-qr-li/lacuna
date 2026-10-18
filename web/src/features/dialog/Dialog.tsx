// In-app confirm / notice dialog (backlog item 13): replaces window.confirm / alert / prompt, which
// show the browser's own "127.0.0.1:8765 says" box. Imperative, like the native calls:
//   if (!(await confirmDialog({ message, danger: true, confirmLabel: t("移出") }))) return;
// It renders into its own root on <body>, so no screen has to mount anything. Esc / the backdrop
// cancel, Enter confirms; focus returns to where it was.
import { useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import { t } from "../../i18n";
import "./dialog.css";

export interface ConfirmOptions {
  message: string;
  title?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** deletes or throws something away: red confirm button */
  danger?: boolean;
}

interface Props extends ConfirmOptions {
  notice?: boolean; // one OK button (alert)
  done: (ok: boolean) => void;
}

export function DialogBox({ message, title, confirmLabel, cancelLabel, danger, notice, done }: Props) {
  const ok = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    ok.current?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); done(false); }
      else if (e.key === "Enter" && !e.isComposing) { e.preventDefault(); e.stopPropagation(); done(true); }
      else if (e.key === "Tab") {
        // keep focus inside the dialog
        const els = [...document.querySelectorAll<HTMLButtonElement>(".dlg button")];
        const i = els.indexOf(document.activeElement as HTMLButtonElement);
        e.preventDefault();
        els[(i + (e.shiftKey ? els.length - 1 : 1)) % els.length]?.focus();
      }
    };
    // capture: the review screen's shortcuts (space, ←/→, K…) must not fire under the dialog
    window.addEventListener("keydown", key, true);
    return () => window.removeEventListener("keydown", key, true);
  }, [done]);
  return (
    <div className="dlg-backdrop" onMouseDown={(e) => e.target === e.currentTarget && done(false)}>
      <div className="dlg" role="alertdialog" aria-modal="true" aria-labelledby="dlg-title" aria-describedby="dlg-msg" data-testid="dialog">
        <h2 id="dlg-title">{title ?? (notice ? t("提示") : danger ? t("确定吗？") : t("确认一下"))}</h2>
        <p id="dlg-msg">{message}</p>
        <div className="dlg-actions">
          {!notice && (
            <button type="button" className="btn btn-outline" onClick={() => done(false)}>
              {cancelLabel ?? t("取消")}
            </button>
          )}
          <button type="button" ref={ok} className={danger ? "btn btn-danger" : "btn btn-primary"} onClick={() => done(true)}>
            {confirmLabel ?? (notice ? t("知道了") : t("确定"))}
          </button>
        </div>
      </div>
    </div>
  );
}

function open(props: Omit<Props, "done">): Promise<boolean> {
  const back = document.activeElement as HTMLElement | null;
  const host = document.createElement("div");
  host.className = "dlg-host";
  document.body.appendChild(host);
  const root = createRoot(host);
  return new Promise((resolve) => {
    let closed = false;
    const done = (v: boolean) => {
      if (closed) return;
      closed = true;
      root.unmount();
      host.remove();
      back?.focus?.();
      resolve(v);
    };
    root.render(<DialogBox {...props} done={done} />);
  });
}

/** Ask before doing something: resolves true on confirm, false on cancel / Esc / backdrop. */
export const confirmDialog = (o: ConfirmOptions | string) => open(typeof o === "string" ? { message: o } : o);

/** Tell the user something; resolves when it is dismissed. */
export const noticeDialog = (message: string, title?: string) => open({ message, title, notice: true }).then(() => undefined);
