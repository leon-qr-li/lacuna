import { Fragment, useState, type ReactNode } from "react";
import { markdownToHtml } from "../../markdown";
import { currentTheme, setTheme } from "../theme/theme";
import { lang, setLang, t } from "../../i18n";
import termsZh from "./docs/terms.zh.md?raw";
import termsEn from "./docs/terms.en.md?raw";
import privacyZh from "./docs/privacy.zh.md?raw";
import privacyEn from "./docs/privacy.en.md?raw";
import "./legal.css";

/** 用户条款 / 隐私政策 (lacuna_app/legal.py, decision 2026-10-25-terms-and-privacy). Both open without signing in
 *  at /legal/terms and /legal/privacy (AuthGate shows them before anything else), in a new tab from the app. */
export type LegalDoc = "terms" | "privacy";

const DOCS: Record<LegalDoc, { zh: string; en: string }> = {
  terms: { zh: termsZh, en: termsEn },
  privacy: { zh: privacyZh, en: privacyEn },
};

export const legalHref = (doc: LegalDoc) => `/legal/${doc}`;

/** The document this page address shows, or null (any other page). */
export function legalPath(): LegalDoc | null {
  const m = /^\/legal\/(terms|privacy)\/?$/.exec(window.location.pathname);
  return m ? (m[1] as LegalDoc) : null;
}

// the parts still to fill in before the lawyer's version (entity, governing law, DMCA agent…): marked on the page
const TBD = /【待定：[^】]*】|\[TBD:[^\]]*\]/g;

/** The document as HTML: markdownToHtml escapes everything first, so only its own tags are left. */
export function legalHtml(doc: LegalDoc, l: "zh" | "en" = lang): string {
  return markdownToHtml(DOCS[doc][l]).replace(TBD, (m) => `<mark class="legal-tbd">${m}</mark>`);
}

// each language is named in itself
const ZH = "中文"; // i18n-ignore

export function LegalPage({ doc }: { doc: LegalDoc }) {
  const [theme, setT] = useState(currentTheme());
  return (
    <div className="legal" data-testid={`legal-${doc}`}>
      <header className="legal-top">
        <a className="legal-logo" href="/">
          <i />
          LACUNA
        </a>
        <nav className="legal-tabs">
          <a href={legalHref("terms")} aria-current={doc === "terms" ? "page" : undefined}>
            {t("用户条款")}
          </a>
          <a href={legalHref("privacy")} aria-current={doc === "privacy" ? "page" : undefined}>
            {t("隐私政策")}
          </a>
        </nav>
        <div className="legal-corner">
          <button type="button" className="btn btn-outline btn-small" onClick={() => setLang(lang === "en" ? "zh" : "en")}>
            {lang === "en" ? ZH : "English"}
          </button>
          <button
            type="button"
            className="btn btn-outline btn-small"
            aria-label={theme === "dark" ? t("浅色") : t("深色")}
            onClick={() => {
              const next = theme === "dark" ? "light" : "dark";
              setTheme(next);
              setT(next);
            }}
          >
            {theme === "dark" ? "☀" : "☾"}
          </button>
        </div>
      </header>
      <article className="legal-doc" dangerouslySetInnerHTML={{ __html: legalHtml(doc) }} />
      <footer className="legal-foot">
        <a href="/">← {t("回到 LACUNA")}</a>
      </footer>
    </div>
  );
}

/** `t()` text with {terms} / {privacy} replaced by links to the documents (opening in a new tab). */
export function withLegalLinks(text: string): ReactNode {
  const link = (doc: LegalDoc) => (
    <a href={legalHref(doc)} target="_blank" rel="noopener" data-testid={`legal-link-${doc}`}>
      {doc === "terms" ? t("用户条款") : t("隐私政策")}
    </a>
  );
  return text.split(/(\{terms\}|\{privacy\})/).map((part, i) => (
    <Fragment key={i}>{part === "{terms}" ? link("terms") : part === "{privacy}" ? link("privacy") : part}</Fragment>
  ));
}

/** The box to tick when creating an account (the first one, or from an invite). */
export function AgreeBox({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="auth-check legal-agree">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} data-testid="legal-agree" />
      <span>{withLegalLinks(t("我已阅读并同意 {terms} 和 {privacy}"))}</span>
    </label>
  );
}
