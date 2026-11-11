import { useEffect, useRef, useState } from "react";
import { t } from "../../i18n";
import { noticeDialog } from "../dialog/Dialog";
import "./episode-name.css";
import { nameApi, type EpisodeName } from "./api";

const Pen = () => (
  <svg
    viewBox="0 0 16 16"
    width="14"
    height="14"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.6"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <path d="M10.5 2.5l3 3L5.5 13.5H2.5v-3z" />
  </svg>
);

/** The episode's name in the top bar; the pencil (or a click on the name) turns it into a field:
 *  Enter saves, Esc cancels. In an album with a naming format only the 名称 is typed. */
export function EpisodeTitle({
  id,
  title,
  readOnly,
  onRenamed,
}: {
  id: string;
  title?: string;
  readOnly?: boolean;
  onRenamed: (v: EpisodeName) => void;
}) {
  const [edit, setEdit] = useState<EpisodeName | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (edit) {
      input.current?.focus();
      input.current?.select();
    }
  }, [edit]);
  const open = async () => {
    if (readOnly || busy) return;
    try {
      const v = await nameApi.get(id);
      setName(v.name);
      setEdit(v);
    } catch (e) {
      await noticeDialog((e as Error).message);
    }
  };
  const save = async () => {
    if (!edit) return;
    if (name.trim() === edit.name) return setEdit(null);
    setBusy(true);
    try {
      const v = await nameApi.set(id, name);
      setEdit(null);
      onRenamed(v);
    } catch (e) {
      await noticeDialog((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  if (edit)
    return (
      <form
        className="ep-title en-inline"
        data-testid="title-edit"
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.stopPropagation();
            setEdit(null);
          }
        }}
      >
        <input
          ref={input}
          value={name}
          maxLength={200}
          placeholder={id}
          aria-label={edit.naming ? t("名称") : t("这一集叫什么")}
          onChange={(e) => setName(e.target.value)}
          data-testid="title-input"
        />
        <button
          type="submit"
          className="btn btn-primary btn-small"
          disabled={busy}
          data-testid="title-save"
        >
          {t("保存")}
        </button>
        <button
          type="button"
          className="btn btn-ghost btn-small"
          onClick={() => setEdit(null)}
        >
          {t("取消")}
        </button>
      </form>
    );
  return (
    <span className="ep-title en-title" data-testid="episode-title">
      {readOnly ? (
        <span className="en-name">{title ?? "…"}</span>
      ) : (
        <>
          <button
            type="button"
            className="en-name en-name-btn"
            onClick={() => void open()}
            title={t("点一下改名")}
          >
            {title ?? "…"}
          </button>
          <button
            type="button"
            className="en-pen"
            onClick={() => void open()}
            aria-label={t("改名")}
            title={t("改名")}
            data-testid="title-pen"
          >
            <Pen />
          </button>
        </>
      )}
    </span>
  );
}
