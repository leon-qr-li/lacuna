// Library scopes (decision library-scopes): 公共 = shared by every episode, 本集 = belongs to the
// listed episodes. The file is stored once; membership is metadata on the asset.
import { useRef, useState } from "react";
import type { Asset, EpisodeRef, ScopeAction } from "./api";
import { libraryApi } from "./api";
import { t } from "../../i18n";
import { BusyLabel } from "../loading/Loading";
import "./scope.css";

const ACCEPT = ".mp3,.wav,.flac,.m4a,.aac,.ogg,.opus,.aif,.aiff,.wma,audio/*";

/** Filter value: "" all, "shared" 公共, or "ep:<id>" one episode's own. */
export type ScopeFilterValue = string;

export function inScope(a: Asset, f: ScopeFilterValue): boolean {
  if (!f) return true;
  if (f === "shared") return a.shared;
  return !a.shared && a.episodes.includes(f.slice(3));
}

const epName = (e: EpisodeRef) => (e.archived ? t("{title}（已归档）", { title: e.title }) : e.title);
const titleOf = (eps: EpisodeRef[], id: string) => eps.find((e) => e.id === id)?.title ?? id;

/** Where an asset belongs: 公共, or the episodes it is in. */
export function ScopeBadge({ a, eps }: { a: Asset; eps: EpisodeRef[] }) {
  return (
    <span className={`badge scope-badge ${a.shared ? "scope-shared" : "scope-episode"}`} data-testid="asset-scope">
      {a.shared ? t("公共") : t("本集：{titles}", { titles: a.episodes.map((id) => titleOf(eps, id)).join("、") })}
    </span>
  );
}

/** 「挪到某一集」 for every asset; 「设为公共」 and 「也加到另一集」 for one that belongs to episodes. */
export function ScopeActions({ a, eps, disabled, onChange }: {
  a: Asset;
  eps: EpisodeRef[];
  disabled: boolean;
  onChange: (p: Promise<{ asset: Asset; message?: string | null }>) => void;
}) {
  const live = eps.filter((e) => !e.archived);
  const moveTo = live.filter((e) => a.shared || a.episodes.length !== 1 || a.episodes[0] !== e.id);
  const addTo = live.filter((e) => !a.episodes.includes(e.id));
  const set = (action: ScopeAction, episode?: string) => onChange(libraryApi.setScope(a.id, action, episode));
  return (
    <div className="row gap8 wrap scope-actions">
      {moveTo.length > 0 && (
        <select
          className="scope-select"
          value=""
          disabled={disabled}
          aria-label={t("挪到某一集")}
          onChange={(e) => e.target.value && set("move", e.target.value)}
        >
          <option value="">{t("挪到某一集…")}</option>
          {moveTo.map((e) => (
            <option key={e.id} value={e.id}>
              {epName(e)}
            </option>
          ))}
        </select>
      )}
      {!a.shared && addTo.length > 0 && (
        <select
          className="scope-select"
          value=""
          disabled={disabled}
          aria-label={t("也加到另一集")}
          onChange={(e) => e.target.value && set("add", e.target.value)}
        >
          <option value="">{t("也加到另一集…")}</option>
          {addTo.map((e) => (
            <option key={e.id} value={e.id}>
              {epName(e)}
            </option>
          ))}
        </select>
      )}
      {!a.shared && (
        <button type="button" className="btn btn-small btn-outline" disabled={disabled} onClick={() => set("share")}>
          {t("设为公共")}
        </button>
      )}
    </div>
  );
}

/** Where new files go on the library page: 公共, or one episode. */
export function ScopeTarget({ eps, value, onChange }: { eps: EpisodeRef[]; value: string; onChange: (v: string) => void }) {
  return (
    <label className="row gap8 small">
      {t("加到")}
      <select value={value} onChange={(e) => onChange(e.target.value)} aria-label={t("新文件加到哪里")} data-testid="scope-target">
        <option value="">{t("公共")}</option>
        {eps
          .filter((e) => !e.archived)
          .map((e) => (
            <option key={e.id} value={e.id}>
              {e.title}
            </option>
          ))}
      </select>
    </label>
  );
}

/** Show all, 公共 only, or one episode's own assets. */
export function ScopeFilter({ eps, value, onChange }: { eps: EpisodeRef[]; value: ScopeFilterValue; onChange: (v: ScopeFilterValue) => void }) {
  return (
    <label className="row gap8 small scope-filter">
      {t("显示")}
      <select value={value} onChange={(e) => onChange(e.target.value)} aria-label={t("按范围筛选")}>
        <option value="">{t("全部")}</option>
        <option value="shared">{t("公共")}</option>
        {eps.map((e) => (
          <option key={e.id} value={`ep:${e.id}`}>
            {epName(e)}
          </option>
        ))}
      </select>
    </label>
  );
}

/** The music page's own upload: the files belong to this episode (本集). */
export function EpisodeUpload({ id, kinds, onAdded }: { id: string; kinds: Record<string, string>; onAdded: (msg: string, asset?: Asset) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState("other");
  const [busy, setBusy] = useState(false);
  const add = async (files: File[]) => {
    setBusy(true);
    const done: string[] = [];
    let last: Asset | undefined;
    for (const f of files) {
      try {
        const r = await libraryApi.uploadAsset(f, kind, "", id);
        last = r.asset;
        done.push(
          r.duplicate && r.asset.shared
            ? t("素材库里已经有这首（公共），这一集直接能用：{name}", { name: r.asset.name })
            : t("已加到这一集：{name}", { name: r.asset.name }),
        );
      } catch (e) {
        done.push(t("没加进去：{name}", { name: f.name }) + `（${(e as Error).message}）`);
      }
    }
    setBusy(false);
    onAdded(done.join("；"), last);
  };
  return (
    <div className="row gap8 wrap scope-upload" data-testid="episode-upload">
      <button type="button" className="btn btn-outline" disabled={busy} onClick={() => input.current?.click()}>
        <BusyLabel busy={busy} label={t("从电脑添加")} busyLabel={t("正在加入…")} />
      </button>
      <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label={t("上传的文件当作")}>
        {Object.entries(kinds).map(([k, v]) => (
          <option key={k} value={k}>
            {v}
          </option>
        ))}
      </select>
      <span className="small muted">{t("只属于这一集；在素材库可以设为公共。")}</span>
      <input
        ref={input}
        type="file"
        multiple
        accept={ACCEPT}
        hidden
        aria-label={t("选择音乐文件")}
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          e.target.value = "";
          if (files.length) void add(files);
        }}
      />
    </div>
  );
}
