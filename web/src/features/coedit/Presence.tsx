import { joinList, t } from "../../i18n";
import "./coedit.css";

/** "Pei 也在这一集": the other people who have this episode open right now. */
export function Presence({ others }: { others: { name: string }[] }) {
  if (!others.length) return null;
  const names = others.map((o) => o.name);
  return (
    <span className="presence" role="status" data-testid="presence" title={t("他们的修改会自动出现在你的页面上")}>
      <span className="presence-dot" aria-hidden="true" />
      {t("{names} 也在这一集", { names: joinList(names) })}
    </span>
  );
}
