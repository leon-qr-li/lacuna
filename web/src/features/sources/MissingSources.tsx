import { useRef, useState } from "react";
import type { Episode } from "../../api";
import { fmt } from "../../api";
import { t } from "../../i18n";
import { missingOf, uploadSource } from "./api";
import "./sources.css";

/**
 * On the episode page when its recordings are not on the server (an episode moved from the desktop
 * whose raw tracks stayed on the computer): says so, names the files, and takes them back. Each file
 * is matched by content, so the order and names picked don't matter.
 */
export function MissingSources({ ep }: { ep: Episode }) {
  const missing = missingOf(ep);
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  if (!missing.length) return null;

  const upload = async (files: File[]) => {
    const errs: string[] = [];
    let left = missing.length;
    for (const f of files) {
      try {
        setBusy(t("正在上传 {name}…", { name: f.name }));
        const next = await uploadSource(ep.id, f, (p) =>
          setBusy(t("正在上传 {name}… {p}%", { name: f.name, p: Math.round(p * 100) })),
        );
        left = missingOf(next).length;
      } catch (e) {
        errs.push(e instanceof Error ? e.message : String(e));
      }
    }
    setBusy(null);
    setErrors(errs);
    // the page's players asked for this audio before and failed: start them afresh
    if (left === 0) window.location.reload();
  };

  return (
    <div className="banner sources-banner" role="alert" data-testid="missing-sources">
      <p>
        {t("这一集的原始音轨不在服务器上（从电脑搬过来时没带上），所以现在放不了声音，配乐、声音和导出也用不了。把下面的文件传上来就好了：")}
      </p>
      <ul>
        {missing.map((m) => (
          <li key={m.media_id}>
            <b>{m.file}</b> · {m.track} · {fmt(m.duration)}
          </li>
        ))}
      </ul>
      <div className="sources-row">
        <button type="button" className="btn btn-primary btn-small" disabled={!!busy} onClick={() => input.current?.click()}>
          {t("选文件上传")}
        </button>
        {busy && <span className="small">{busy}</span>}
        <input
          ref={input}
          type="file"
          accept="audio/*,.wav,.flac,.mp3,.m4a,.aif,.aiff"
          multiple
          hidden
          data-testid="missing-sources-input"
          onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            e.target.value = "";
            if (files.length) void upload(files);
          }}
        />
      </div>
      {errors.map((m, i) => (
        <p key={i} className="sources-error">
          {m}
        </p>
      ))}
    </div>
  );
}
