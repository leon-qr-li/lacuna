import { lang as uiLang, t, type Lang } from "../../i18n";

// each language is named in itself
const NAMES: [Lang, string][] = [
  ["zh", "中文邮件"], // i18n-ignore
  ["en", "English email"],
];

/** Which language the invite email is written in; starts at the inviter's interface language. */
export function MailLang({ value, onChange }: { value: Lang; onChange: (l: Lang) => void }) {
  return (
    <select aria-label={t("邀请邮件的语言")} value={value} onChange={(e) => onChange(e.target.value as Lang)} data-testid="invite-lang">
      {NAMES.map(([l, name]) => (
        <option key={l} value={l}>
          {name}
        </option>
      ))}
    </select>
  );
}

export const defaultMailLang: Lang = uiLang;
