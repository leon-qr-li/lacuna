import { useEffect, useRef, useState } from "react";
import { t } from "../../i18n";
import { confirmDialog } from "../dialog/Dialog";
import type { ActionId, Group, Refusal } from "./keys";
import { ACTIONS, actionOf, check, comboOf, isChanged, isMac, keyLabel, keysOf, save, snapshot, useShortcuts } from "./keys";
import "./shortcuts.css";

const GROUPS: { id: Group; name: () => string; where: () => string }[] = [
  { id: "play", name: () => t("播放"), where: () => t("试听和剪辑页") },
  { id: "edit", name: () => t("剪辑"), where: () => t("试听和剪辑页") },
  { id: "any", name: () => t("撤销"), where: () => t("所有页面") },
  { id: "review", name: () => t("审阅"), where: () => t("审阅页") },
];
const groupName = (id: ActionId) => GROUPS.find((g) => g.id === actionOf(id).group)!.name();

type Slot = { id: ActionId; i: number };
type Pop = (Slot & { combo: string; why: NonNullable<Refusal> }) | null;

/**
 * 设置 → 快捷键 (decision 2026-11-02-custom-shortcuts, design A): the customizable keys grouped by page; a click on a
 * key records a new one (Esc cancels). A key used on the same page asks first; browser keys are refused. Popovers
 * float over the rows, so nothing below moves.
 */
export function ShortcutsCard() {
  useShortcuts();
  const [rec, setRec] = useState<Slot | null>(null);
  const [pop, setPop] = useState<Pop>(null);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const box = useRef<HTMLDivElement | null>(null);

  const put = async (next: ReturnType<typeof snapshot>, note: string) => {
    setErr(null);
    try {
      await save(next);
      setDone(note);
    } catch (e) {
      setErr(t("没保存上：{message}", { message: (e as Error).message }));
    }
  };
  const give = (s: Slot, combo: string, from: ActionId[] = []) => {
    const next = snapshot();
    for (const o of from) next[o] = (next[o] ?? []).filter((k) => k !== combo);
    const mine = next[s.id] ?? [];
    if (!mine.includes(combo)) {
      if (s.i < mine.length) mine[s.i] = combo;
      else mine.push(combo);
    }
    next[s.id] = mine.slice(0, 2);
    setRec(null);
    setPop(null);
    void put(next, t("已改成 {k}", { k: keyLabel(combo) }));
  };

  // while recording: the next key (Esc cancels); nothing else on the page reacts to it
  useEffect(() => {
    if (!rec) return;
    const on = (e: KeyboardEvent) => {
      e.preventDefault();
      e.stopImmediatePropagation();
      if (e.key === "Escape") {
        setRec(null);
        setPop(null);
        return;
      }
      if (e.repeat) return;
      const combo = comboOf(e);
      if (!combo) return;
      const why = check(rec.id, combo);
      if (why) setPop({ ...rec, combo, why });
      else give(rec, combo);
    };
    const away = (e: PointerEvent) => {
      if (!(e.target as HTMLElement).closest?.(".sk-keys")) {
        setRec(null);
        setPop(null);
      }
    };
    window.addEventListener("keydown", on, true);
    window.addEventListener("pointerdown", away);
    return () => {
      window.removeEventListener("keydown", on, true);
      window.removeEventListener("pointerdown", away);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rec]);

  const remove = (s: Slot) => {
    const next = snapshot();
    next[s.id] = (next[s.id] ?? []).filter((_, i) => i !== s.i);
    setRec(null);
    setPop(null);
    void put(next, t("已删掉这个键"));
  };
  const resetOne = (id: ActionId) => {
    const next = snapshot();
    next[id] = [...actionOf(id).defaults];
    setRec(null);
    setPop(null);
    void put(next, t("已恢复默认"));
  };
  const resetAll = async () => {
    const n = ACTIONS.filter((a) => isChanged(a.id)).length;
    if (!n) return;
    if (!(await confirmDialog({ title: t("全部恢复默认？"), message: t("你改过的 {n} 个快捷键会变回默认。", { n }), confirmLabel: t("恢复默认") }))) return;
    setRec(null);
    setPop(null);
    void put(Object.fromEntries(ACTIONS.map((a) => [a.id, [...a.defaults]])), t("已恢复默认"));
  };

  const hint = isMac() ? t("Esc 取消。⌘、⇧、⌥ 加一个键也行。") : t("Esc 取消。Ctrl、Shift、Alt 加一个键也行。");
  const popover = (s: Slot) => {
    if (pop && pop.id === s.id && pop.i === s.i) {
      const k = <kbd>{keyLabel(pop.combo)}</kbd>;
      if (pop.why.kind !== "taken")
        return (
          <div className="sk-pop is-err" role="alert" data-testid="shortcut-refused">
            <strong className="sk-pop-title">
              {k}
              {pop.why.kind === "reserved" ? t("这个键浏览器自己要用") : t("这个键用来操作按钮")}
            </strong>
            <span className="muted">{t("换一个吧，比如加上 Shift。")}</span>
            <div className="sk-pop-acts">
              <button type="button" className="btn btn-outline btn-small" onClick={() => setPop(null)}>
                {t("再按一个")}
              </button>
            </div>
          </div>
        );
      const other = pop.why.by[0];
      const leaves = pop.why.by.some((o) => keysOf(o).length === 1);
      return (
        <div className="sk-pop is-warn" role="alert" data-testid="shortcut-conflict">
          <strong className="sk-pop-title">
            {k}
            {t("这个键已经在用")}
          </strong>
          <span>
            {t("已经用在「{action}」。", { action: `${groupName(other)} · ${actionOf(other).label()}` })}
            {leaves && <span className="muted"> {t("那边会变成「未设置」。")}</span>}
          </span>
          <div className="sk-pop-acts">
            <button type="button" className="btn btn-outline btn-small" onClick={() => setPop(null)} data-testid="shortcut-conflict-cancel">
              {t("取消")}
            </button>
            <button type="button" className="btn btn-primary btn-small" onClick={() => give(pop, pop.combo, pop.why.kind === "taken" ? pop.why.by : [])} data-testid="shortcut-take">
              {t("改用在这里")}
            </button>
          </div>
        </div>
      );
    }
    if (rec && rec.id === s.id && rec.i === s.i)
      return (
        <div className="sk-pop" data-testid="shortcut-recording">
          <strong className="sk-pop-title">{t("按下新的组合键")}</strong>
          <span className="muted">{hint}</span>
          <div className="sk-pop-acts">
            {s.i < keysOf(s.id).length && (
              <button type="button" className="btn btn-outline btn-small" onClick={() => remove(s)} data-testid="shortcut-remove">
                {t("删掉这个键")}
              </button>
            )}
            <button type="button" className="btn btn-outline btn-small" onClick={() => (setRec(null), setPop(null))}>
              {t("取消")}
            </button>
          </div>
        </div>
      );
    return null;
  };

  const row = (id: ActionId) => {
    const a = actionOf(id);
    const ks = keysOf(id);
    const slots: { i: number; label: string; cls: string }[] = [];
    for (let i = 0; i < 2; i++) {
      const on = rec?.id === id && rec.i === i;
      if (on) slots.push({ i, label: t("按下新的组合键…"), cls: "is-rec" });
      else if (i < ks.length) slots.push({ i, label: keyLabel(ks[i]), cls: a.defaults.includes(ks[i]) ? "" : "is-changed" });
      else if (i === 0) slots.push({ i, label: t("未设置"), cls: "is-none" });
      else if (i === ks.length) slots.push({ i, label: t("＋ 再加一个"), cls: "is-add" });
    }
    const open = (pop?.id === id ? pop.i : rec?.id === id ? rec.i : -1) as number;
    return (
      <div key={id} className="sk-row" data-testid={`shortcut-${id}`}>
        <span className="sk-label">
          {!ks.length && <span className="sk-dot" aria-hidden />}
          {a.label()}
        </span>
        <span className="sk-keys">
          {slots.map((s) => (
            <button
              key={s.i}
              type="button"
              className={`sk-key ${s.cls}`}
              title={s.label}
              aria-label={`${a.label()}: ${s.label}`}
              onClick={() => {
                setPop(null);
                setRec(rec?.id === id && rec.i === s.i ? null : { id, i: s.i });
              }}
              data-testid={`shortcut-${id}-${s.i}`}
            >
              {s.label}
            </button>
          ))}
          {open >= 0 && popover({ id, i: open })}
        </span>
        <button
          type="button"
          className={`sk-reset ${isChanged(id) ? "" : "is-hidden"}`}
          title={t("恢复默认")}
          aria-label={t("恢复默认")}
          tabIndex={isChanged(id) ? 0 : -1}
          onClick={() => resetOne(id)}
          data-testid={`shortcut-${id}-reset`}
        >
          ↺
        </button>
      </div>
    );
  };

  const mod = isMac() ? "⌘" : "Ctrl";
  return (
    <div className="sk" ref={box} data-testid="shortcuts-card">
      <div className="sk-top">
        <p className="muted small">{t("点一个键，再按键盘上新的组合键。只对你自己生效，换电脑也一样。")}</p>
        <button type="button" className="btn btn-outline btn-small" onClick={() => void resetAll()} disabled={!ACTIONS.some((a) => isChanged(a.id))} data-testid="shortcuts-reset-all">
          ↺ {t("全部恢复默认")}
        </button>
      </div>
      <p className={`sk-status small ${err ? "error" : "muted"}`} role="status" aria-live="polite">
        {err ?? done ?? ""}
      </p>
      {GROUPS.map((g) => (
        <section key={g.id} className="card sk-group" aria-label={g.name()}>
          <div className="sk-group-head">
            <h2>{g.name()}</h2>
            <span className="muted small">{g.where()}</span>
          </div>
          {ACTIONS.filter((a) => a.group === g.id).map((a) => row(a.id))}
        </section>
      ))}
      <section className="card sk-group" aria-label={t("这些用鼠标或固定不变")}>
        <div className="sk-group-head">
          <h2>{t("这些用鼠标或固定不变")}</h2>
        </div>
        <div className="sk-fixed small">
          {[
            ["Esc", t("取消选中、关掉弹窗")],
            [`${mod} + ${t("滚轮")}`, t("放大 / 缩小时间线")],
            [t("按住空格拖"), t("左右移动时间线")],
            [t("拖选区的边"), t("调整选区")],
            [t("右键空白处"), t("加入间隙（选长度）")],
          ].map(([k, v]) => (
            <span key={k}>
              <kbd>{k}</kbd>
              {v}
            </span>
          ))}
        </div>
      </section>
      <p className="muted small">{t("在输入框里打字时快捷键不生效。")}</p>
    </div>
  );
}
