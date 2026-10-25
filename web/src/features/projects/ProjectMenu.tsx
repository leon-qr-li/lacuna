import { useEffect, useRef, useState } from "react";
import { t } from "../../i18n";
import { ProjectAvatar } from "./Avatar";
import { NewProjectDialog } from "./NewProject";
import { openProject, useProjects } from "./api";

/** Top bar, after LACUNA: the project you are in. Its menu switches project, opens 所有项目 and
 *  项目设置, and starts a new project. Nothing without accounts (no projects to tell apart). */
export function ProjectCrumb() {
  const sp = useProjects();
  const [open, setOpen] = useState(false);
  const [making, setMaking] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    const key = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", key);
    };
  }, [open]);
  if (!sp?.current) return null;
  const cur = sp.current;
  const go = (href: string) => {
    setOpen(false);
    window.location.hash = href;
  };
  return (
    <>
      <span className="crumb-sep" aria-hidden="true">
        /
      </span>
      <span className="prj-crumb" ref={box}>
        <button
          type="button"
          className="prj-crumb-btn"
          aria-haspopup="menu"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
          data-testid="project-menu"
          title={t("节目")}
        >
          <ProjectAvatar p={cur} size={22} />
          <span className="prj-crumb-name">{cur.name}</span>
          {cur.archived && (
            <span className="prj-tag" data-testid="project-archived-tag">
              {t("已归档 · 只读")}
            </span>
          )}
          <span aria-hidden="true" className="prj-caret">
            ▾
          </span>
        </button>
        {open && (
          <div className="prj-menu" role="menu" aria-label={t("节目")}>
            <div className="prj-menu-head">{t("我的节目")}</div>
            {sp.mine.map((p) => (
              <button
                key={p.id}
                type="button"
                role="menuitemradio"
                aria-checked={p.id === cur.id}
                className="prj-menu-item prj-menu-row"
                onClick={() => (p.id === cur.id ? go("#/") : void openProject(p.id))}
              >
                <span className="prj-check" aria-hidden="true">
                  {p.id === cur.id ? "✓" : ""}
                </span>
                <ProjectAvatar p={p} size={20} />
                <span className="prj-menu-name">{p.name}</span>
                {p.archived ? <span className="prj-tag">{t("已归档")}</span> : <span />}
              </button>
            ))}
            <hr />
            <button type="button" role="menuitem" className="prj-menu-item" onClick={() => go("#/projects")} data-testid="project-all-link">
              <span className="prj-check" aria-hidden="true" />
              {t("我的节目")}
            </button>
            <button type="button" role="menuitem" className="prj-menu-item" onClick={() => go("#/project")} data-testid="project-settings-link">
              <span className="prj-check" aria-hidden="true" />
              {t("节目设置")}
            </button>
            <button
              type="button"
              role="menuitem"
              className="prj-menu-item"
              onClick={() => {
                setOpen(false);
                setMaking(true);
              }}
              data-testid="project-new"
            >
              <span className="prj-check" aria-hidden="true" />
              {t("＋ 新节目")}
            </button>
          </div>
        )}
      </span>
      {making && <NewProjectDialog onClose={() => setMaking(false)} />}
    </>
  );
}
