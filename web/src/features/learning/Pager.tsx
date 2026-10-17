import { t } from "../../i18n";

export const PAGE_SIZE = 10;

/** Page numbers to show: all when few, else first, last and the neighbours of the current one, with gaps. */
export function pageItems(page: number, pages: number): (number | null)[] {
  if (pages <= 7) return Array.from({ length: pages }, (_, i) => i);
  const keep = new Set([0, pages - 1, page - 1, page, page + 1].filter((p) => p >= 0 && p < pages));
  const out: (number | null)[] = [];
  let last = -1;
  for (const p of [...keep].sort((a, b) => a - b)) {
    if (p - last > 1) out.push(null);
    out.push(p);
    last = p;
  }
  return out;
}

/** Shown only when a group holds more than one page of rules. */
export function Pager({ page, total, onPage }: { page: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.ceil(total / PAGE_SIZE);
  if (pages <= 1) return null;
  const from = page * PAGE_SIZE + 1;
  const to = Math.min(total, (page + 1) * PAGE_SIZE);
  return (
    <nav className="pager" aria-label={t("翻页")}>
      <span className="small muted">{t("第 {from}–{to} 条，共 {total} 条", { from, to, total })}</span>
      <span className="row gap4">
        <button type="button" className="btn btn-outline" disabled={page === 0} onClick={() => onPage(page - 1)}>
          {t("上一页")}
        </button>
        {pageItems(page, pages).map((p, i) =>
          p === null ? (
            <span key={`gap${i}`} className="pager-gap muted">…</span>
          ) : (
            <button key={p} type="button" className={`pager-num${p === page ? " on" : ""}`} aria-current={p === page ? "page" : undefined} onClick={() => onPage(p)}>
              {p + 1}
            </button>
          ),
        )}
        <button type="button" className="btn btn-outline" disabled={page === pages - 1} onClick={() => onPage(page + 1)}>
          {t("下一页")}
        </button>
      </span>
    </nav>
  );
}
