import { useEffect, useState, type ReactNode } from "react";
import { t } from "../../i18n";

/** The top bar's links. On wide screens they sit in the bar as before; on a phone they fold behind a menu
 *  button so the bar stays one line (batch 7, T9). */
export function MenuNav({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const close = () => setOpen(false);
    window.addEventListener("hashchange", close);
    return () => window.removeEventListener("hashchange", close);
  }, []);
  return (
    <>
      <button
        type="button"
        className="btn btn-ghost topnav-toggle"
        aria-expanded={open}
        aria-label={open ? t("收起菜单") : t("菜单")}
        onClick={() => setOpen(!open)}
        data-testid="menu-toggle"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" aria-hidden="true">
          {open ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
        </svg>
      </button>
      <div className={`topnav${open ? " is-open" : ""}`} onClick={(e) => (e.target as HTMLElement).closest("a") && setOpen(false)}>
        {children}
      </div>
    </>
  );
}
