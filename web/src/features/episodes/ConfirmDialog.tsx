import { useEffect, useRef, type ReactNode } from "react";
import { t } from "../../i18n";

/**
 * An in-app confirmation (no browser confirm()). `danger` paints the confirm button red.
 * Esc or a click outside cancels; the cancel button has the focus, so Enter never deletes by accident.
 */
export function ConfirmDialog({
  title,
  children,
  confirmLabel,
  danger,
  busy,
  onConfirm,
  onCancel,
}: {
  title: string;
  children: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const cancel = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    cancel.current?.focus();
    const key = (e: KeyboardEvent) => e.key === "Escape" && onCancel();
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [onCancel]);
  return (
    <div className="ep-dialog-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onCancel()}>
      <div className="ep-dialog card" role="alertdialog" aria-modal="true" aria-labelledby="ep-dialog-title">
        <h2 id="ep-dialog-title">{title}</h2>
        <div className="ep-dialog-body">{children}</div>
        <div className="row gap8 ep-dialog-actions">
          <button ref={cancel} type="button" className="btn" onClick={onCancel} disabled={busy}>
            {t("取消")}
          </button>
          <button type="button" className={`btn ${danger ? "btn-danger" : "btn-primary"}`} onClick={onConfirm} disabled={busy}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
