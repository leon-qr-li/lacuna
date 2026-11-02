import { useEffect, useState, type ReactNode } from "react";
import { t } from "../../i18n";
import "./episode-name.css";
import { RENAMED, nameApi, type EpisodeName } from "./api";

type Choice = { title: string; tag: string };

/** 发布资料 → 标题: LACUNA's titles (and the user's own name first) as one pick list. Picking one renames
 *  the episode everywhere (home card, episode page, the publish pack's title), with an undo. */
export function PublishTitle({
  id,
  title,
  suggested,
  busy,
  onRenamed,
  copyButton,
}: {
  id: string;
  /** the pack's title now */
  title: string;
  /** LACUNA's titles as written (its own pick first) */
  suggested: string[];
  busy?: boolean;
  /** the episode got this name: reload the pack, update the top bar */
  onRenamed: (v: EpisodeName) => void;
  copyButton: ReactNode;
}) {
  const [v, setV] = useState<EpisodeName | null>(null);
  const [own, setOwn] = useState("");
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<{
    msg: string;
    back: string | null;
  } | null>(null);
  useEffect(() => {
    let alive = true;
    // the pack's title changed (a fix from the name check, another member): the episode's name may have too
    nameApi.get(id).then(
      (x) => {
        if (!alive) return;
        setV(x);
        window.dispatchEvent(
          new CustomEvent<EpisodeName>(RENAMED, { detail: x }),
        );
      },
      () => undefined,
    );
    return () => {
      alive = false;
    };
  }, [id, title]);

  const named = !!v?.named;
  const list: Choice[] = [];
  if (named && v && !suggested.includes(v.name))
    list.push({ title: v.name, tag: t("你起的") });
  suggested.forEach((s, i) =>
    list.push({ title: s, tag: i === 0 ? t("LACUNA 推荐") : "" }),
  );
  // older packs (and a pack without AI) list only the pack's title
  if (!list.length && title) list.push({ title, tag: "" });
  const current = named ? (v?.name ?? null) : null;

  const pick = async (name: string, undo = false) => {
    if (!v || saving || (name === current && !undo)) return;
    const back = named ? v.name : "";
    setSaving(true);
    try {
      const nv = await nameApi.set(id, name);
      setV(nv);
      onRenamed(nv);
      setToast(
        undo
          ? { msg: t("已撤销"), back: null }
          : {
              msg: t("已改名为「{title}」，主页和剧集页也换了", {
                title: nv.title,
              }),
              back,
            },
      );
    } catch (e) {
      setToast({ msg: (e as Error).message, back: null });
    } finally {
      setSaving(false);
    }
  };

  return (
    <section
      className="card"
      aria-label={t("标题")}
      data-tour="publish-title-card"
    >
      <div className="card-head">
        <strong>{t("标题")}</strong>
        {copyButton}
      </div>
      <div className="en-body">
        {v && !named && (
          <p className="en-banner small" data-testid="publish-unnamed">
            {t("这一集还没起名。挑一个，主页和剧集页都会换成这个名字。")}
          </p>
        )}
        <div
          className="en-choices"
          role="radiogroup"
          aria-label={t("标题")}
          data-testid="publish-titles"
        >
          {list.map((c) => (
            <button
              key={c.title}
              type="button"
              role="radio"
              aria-checked={c.title === current}
              className="en-choice"
              disabled={busy || saving || !v}
              onClick={() => void pick(c.title)}
              data-testid="publish-title-choice"
            >
              <span className="en-dot" aria-hidden="true" />
              <span
                className="en-choice-text"
                data-testid={c.title === current ? "publish-title" : undefined}
              >
                {c.title}
              </span>
              {c.tag && <span className="en-tag small">{c.tag}</span>}
            </button>
          ))}
        </div>
        <form
          className="en-own"
          onSubmit={(e) => {
            e.preventDefault();
            const n = own.trim();
            if (n) void pick(n).then(() => setOwn(""));
          }}
        >
          <input
            value={own}
            maxLength={200}
            onChange={(e) => setOwn(e.target.value)}
            placeholder={t("自己写一个")}
            aria-label={t("自己写一个")}
            data-testid="publish-title-own"
          />
          <button
            type="submit"
            className="btn btn-outline btn-small"
            disabled={!own.trim() || saving || !v}
          >
            {t("用这个")}
          </button>
        </form>
        {toast && (
          <div
            className="en-toast small"
            role="status"
            data-testid="publish-title-toast"
          >
            <span>{toast.msg}</span>
            {toast.back !== null && (
              <button
                type="button"
                className="btn btn-small"
                disabled={saving}
                onClick={() => void pick(toast.back ?? "", true)}
              >
                {t("撤销")}
              </button>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
