import { t } from "../../i18n";
import { formatTitle, MAX_PART, PRESETS, type Naming, type Preset } from "./api";
import "./album-naming.css";

/**
 * 专辑设置 → 剧集命名 (Leon 2026-10-31): how episodes imported into this album are named. Presets (编号 + 空格 +
 * 名称 first, Leon's own), 不统一 (titles as typed) and 自定义, where the user types what goes before the
 * number, between number and name and after the name. Every choice shows the title it makes.
 */
export function NamingField({ value, onChange, sampleId }: { value: Naming | null; onChange: (n: Naming | null) => void; sampleId: string }) {
  const sample = t("奥本海默");
  const custom = value?.preset === "custom" ? value : null;
  const choose = (p: Preset | "") =>
    onChange(p === "" ? null : p === "custom" ? { preset: "custom", before: custom?.before ?? "", between: custom?.between ?? " - ", after: custom?.after ?? "" } : { preset: p });
  const label: Record<Preset, string> = {
    space: t("编号 + 空格 + 名称"),
    dot: t("编号 · 名称"),
    bar: t("编号｜名称"),
    colon: t("编号：名称"),
    issue: t("第几期 + 名称"),
    name: t("只用名称"),
    custom: t("自定义"),
  };
  const opt = (p: Preset | "", text: string, example: string) => (
    <label key={p || "none"} className={`nm-opt ${(value?.preset ?? "") === p ? "is-on" : ""}`}>
      <input type="radio" name="album-naming" checked={(value?.preset ?? "") === p} onChange={() => choose(p)} data-testid={`naming-${p || "none"}`} />
      <span className="nm-opt-label">{text}</span>
      <span className="nm-opt-ex">{example}</span>
    </label>
  );
  const part = (k: "before" | "between" | "after", text: string) => (
    <label className="nm-part">
      <span className="small muted">{text}</span>
      <input
        value={custom?.[k] ?? ""}
        maxLength={MAX_PART}
        onChange={(e) => onChange({ ...(custom ?? { preset: "custom" }), preset: "custom", [k]: e.target.value })}
        data-testid={`naming-${k}`}
      />
    </label>
  );
  return (
    <fieldset className="alb-field nm" data-testid="album-naming">
      <legend className="alb-label">{t("剧集命名")}</legend>
      <p className="small muted nm-hint">{t("导入到这个专辑的新剧集按这个格式起名：编号是导入时的「剧集编号」，名称是填的标题。")}</p>
      <div className="nm-grid">
        {PRESETS.map((p) => opt(p, label[p], formatTitle({ preset: p }, sampleId, sample)))}
        {opt("custom", label.custom, custom ? formatTitle(custom, sampleId, sample) : t("自己填分隔符和前后的字"))}
        {opt("", t("不统一"), t("照导入时填的标题"))}
      </div>
      {custom && (
        <div className="nm-custom">
          {part("before", t("编号前面"))}
          <span className="nm-token mono">{sampleId}</span>
          {part("between", t("编号和名称之间"))}
          <span className="nm-token">{t("名称")}</span>
          {part("after", t("名称后面"))}
          <p className="nm-preview small" data-testid="naming-preview">
            {t("会叫：{title}", { title: formatTitle(custom, sampleId, sample) })}
          </p>
        </div>
      )}
    </fieldset>
  );
}
