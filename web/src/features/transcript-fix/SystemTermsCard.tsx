import { useEffect, useState } from "react";
import { t } from "../../i18n";
import { transcriptFixApi } from "./api";
import type { SystemTerms } from "./api";
import "./transcript-fix.css";

/**
 * 系统专有名词 on 设置 (decision transcript-terms): names every project's transcripts must spell right, for the
 * whole installation; everyone sees them, only the site owner / admins change them. One per line.
 */
export function SystemTermsCard() {
  const [data, setData] = useState<SystemTerms | null>(null);
  const [text, setText] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    transcriptFixApi
      .systemTerms()
      .then((d) => {
        setData(d);
        setText(d.terms.join("\n"));
      })
      .catch(() => setData(null));
  }, []);

  if (!data) return null;
  const terms = text.split("\n").map((s) => s.trim()).filter(Boolean);
  const dirty = terms.join("\n") !== data.terms.join("\n");
  const save = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const d = await transcriptFixApi.saveSystemTerms(terms);
      setData(d);
      setText(d.terms.join("\n"));
      setMsg(t("已保存，之后打开的剧集会按新词表自动校对。"));
    } catch (e) {
      setMsg(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="card" aria-label={t("系统专有名词")} data-testid="system-terms">
      <div className="card-head">
        <h2>{t("系统专有名词")}</h2>
        <span className="muted small">{t("{n} 个词", { n: data.terms.length })}</span>
      </div>
      <p className="muted small">
        {t("所有节目的逐字稿都会按这些词自动校对，比如 ChatGPT。一行一个。")}
        {!data.can_edit && " " + t("只有管理员能修改。")}
      </p>
      <textarea
        className="tf-terms"
        rows={Math.min(12, Math.max(4, terms.length + 1))}
        value={text}
        readOnly={!data.can_edit}
        onChange={(e) => setText(e.target.value)}
        data-testid="system-terms-text"
        spellCheck={false}
      />
      {data.can_edit && (
        <div className="row">
          <button type="button" className="btn btn-primary btn-small" disabled={busy || !dirty} onClick={() => void save()} data-testid="system-terms-save">
            {t("保存词表")}
          </button>
          {msg && (
            <span className="muted small" role="status">
              {msg}
            </span>
          )}
        </div>
      )}
    </section>
  );
}
