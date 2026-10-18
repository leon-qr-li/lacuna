// 本集学到的规则 (首次检测 #12): a step between 整集试听 and 配乐. LACUNA reads this episode's chat and review
// decisions and proposes the habits it teaches, each with its evidence; Leon adopts, edits or skips each.
// Skippable: nothing later in the flow waits for it.
import { useCallback, useEffect, useRef, useState } from "react";
import { fmt } from "../../api";
import { t } from "../../i18n";
import { BusyLabel, Waiting } from "../loading/Loading";
import type { Lesson, LessonEdit, LessonsView as View } from "./api";
import { lessonsApi } from "./api";
import { TalkBox } from "./TalkBox";

const RELATION: Record<Lesson["relation"], string> = {
  new: t("新规则"),
  reinforce: t("强化已有规则"),
  conflict: t("和已有规则冲突"),
};

const VERDICT: Record<LessonEdit["verdict"], string> = {
  kept: t("AI 删了，你保留了这处删除"),
  restored: t("AI 删了，你恢复了"),
  accepted: t("AI 建议删，你采纳了"),
  declined: t("AI 建议删，你没采纳"),
  added: t("你让 LACUNA 改的"),
};

export function LessonsView({ id, pauseMain }: { id: string; pauseMain: () => void }) {
  const [v, setV] = useState<View | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const started = useRef(false);

  const load = useCallback(async () => {
    try {
      let r = await lessonsApi.view(id);
      if (r.state === "none" && !started.current) {
        started.current = true; // first visit: start right away, no extra click
        r = await lessonsApi.run(id);
      }
      setV(r);
      setErr(null);
    } catch (e) {
      setErr((e as Error).message);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    if (v?.state !== "running") return;
    const h = window.setTimeout(load, 1200);
    return () => window.clearTimeout(h);
  }, [v, load]);

  const rerun = async () => {
    try {
      setV(await lessonsApi.run(id));
    } catch (e) {
      setErr((e as Error).message);
    }
  };
  const put = (x: Lesson) => setV((cur) => cur && { ...cur, lessons: cur.lessons.map((l) => (l.id === x.id ? { ...l, ...x } : l)) });

  const open = v?.lessons.filter((x) => x.state === "draft") ?? [];
  const done = v?.lessons.filter((x) => x.state !== "draft") ?? [];

  return (
    <main className="lessons" data-testid="lessons">
      <header className="lessons-head">
        <h2>{t("本集学到的规则")}</h2>
        <p className="muted">
          {t("这一集剪完了。LACUNA 根据你们的对话和你的审阅决定，总结出下面这些剪辑习惯。逐条看：满意就「采用」，想改可以直接改字，或者跟 LACUNA 说怎么改。")}
        </p>
        <p className="small muted">{t("不想现在看也没关系，直接去配乐，不影响后面的步骤。采用的规则从下一期的 AI 初剪开始照做；想撤回去「学到的规则」。")}</p>
      </header>

      {err && <p className="error">{t("出错了：{message}", { message: err })}</p>}
      {!v && !err && <Waiting label={t("正在打开…")} />}
      {v?.state === "running" && (
        <Waiting label={t("LACUNA 正在回顾这一集的对话和你的审阅决定…")} hint={t("通常半分钟左右")} />
      )}
      {v?.state === "demo" && <p className="card muted">{t("这是演示剧集，不从它学习。")}</p>}
      {v?.state === "no_key" && (
        <div className="card row gap8 wrap lessons-note">
          <span className="grow">{t("现在没接上 AI（没找到 API key），没法总结。在「设置」里填好后再点重试。")}</span>
          <button type="button" className="btn btn-outline" onClick={rerun}>
            {t("重试")}
          </button>
        </div>
      )}
      {v?.state === "error" && (
        <div className="card row gap8 wrap lessons-note">
          <span className="grow error">{t("总结没成功：{message}", { message: v.error ?? "" })}</span>
          <button type="button" className="btn btn-outline" onClick={rerun}>
            {t("重试")}
          </button>
        </div>
      )}
      {v?.state === "done" && (
        <>
          <div className="row gap8 wrap lessons-bar">
            <span className="grow small muted" role="status">
              {open.length
                ? t("{n} 条等你看", { n: open.length })
                : v.lessons.length
                  ? t("都看完了")
                  : t("这一集没看出新的长期习惯。")}
            </span>
            {v.stale && <span className="chip chip-warn">{t("这之后又有新的对话或审阅")}</span>}
            <button type="button" className="btn btn-outline" onClick={rerun} data-testid="lessons-rerun">
              {t("重新总结")}
            </button>
          </div>
          {open.length > 0 && (
            <ul className="lessons-list" aria-label={t("等你看的规则")}>
              {open.map((x) => (
                <LessonCard key={x.id} epId={id} x={x} onChange={put} pauseMain={pauseMain} />
              ))}
            </ul>
          )}
          {done.length > 0 && (
            <>
              <h3 className="lessons-sub">{t("已处理")}</h3>
              <ul className="lessons-list" aria-label={t("已处理")}>
                {done.map((x) => (
                  <LessonCard key={x.id} epId={id} x={x} onChange={put} pauseMain={pauseMain} />
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </main>
  );
}

function LessonCard({ epId, x, onChange, pauseMain }: { epId: string; x: Lesson; onChange: (x: Lesson) => void; pauseMain: () => void }) {
  const [mode, setMode] = useState<"view" | "edit" | "talk">("view");
  const [draft, setDraft] = useState(x.title);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const act = async (what: string, call: () => Promise<Lesson>) => {
    setBusy(what);
    setErr(null);
    try {
      onChange(await call());
      setMode("view");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  };
  const n = x.turns.length + x.edits.length;
  const relation =
    x.relation === "new"
      ? null
      : x.relation === "reinforce"
        ? t("已有规则：「{title}」", { title: x.related_title })
        : t("和已有规则「{title}」冲突：采用后以这条为准。", { title: x.related_title });

  return (
    <li className={`card lesson is-${x.state}`} data-testid="lesson">
      <div className="lesson-tags row gap8 wrap">
        <span className={`chip lesson-rel rel-${x.relation}`}>{RELATION[x.relation]}</span>
        {x.edited && <span className="chip chip-plain">{t("改过")}</span>}
        {x.state === "adopted" && <span className="chip chip-ok">{t("已采用，已生效")}</span>}
        {x.state === "skipped" && <span className="chip chip-plain">{t("已跳过")}</span>}
      </div>
      {mode === "edit" ? (
        <div className="lesson-edit">
          <label className="small muted" htmlFor={`lesson-${x.id}`}>
            {t("规则怎么写")}
          </label>
          <input id={`lesson-${x.id}`} value={draft} onChange={(e) => setDraft(e.target.value)} maxLength={300} />
          <div className="row gap8 wrap">
            <button type="button" className="btn btn-primary" disabled={!draft.trim() || !!busy}
              onClick={() => act("save", () => lessonsApi.edit(epId, x.id, draft))}>
              <BusyLabel busy={busy === "save"} label={t("保存")} />
            </button>
            <button type="button" className="btn btn-outline" onClick={() => setMode("view")}>
              {t("取消")}
            </button>
          </div>
        </div>
      ) : (
        <h3 className="lesson-title" data-testid="lesson-title">{x.title}</h3>
      )}
      {relation && <p className="small lesson-related">{relation}</p>}
      {x.reply && <p className="lesson-reply">{x.reply}</p>}
      {x.why && <p className="prose lesson-why">{x.why}</p>}
      {n > 0 && (
        <details className="lesson-evidence">
          <summary className="small">{t("依据（{n}）", { n })}</summary>
          <ul className="small">
            {x.turns.map((u) => (
              <li key={`t${u.turn}`}>
                <span className="mono muted">@ {fmt(u.at)}</span> {t("你说：「{said}」", { said: u.said })}
              </li>
            ))}
            {x.edits.map((e) => (
              <li key={e.edit}>
                {e.raw && <span className="mono muted">{t("原始")} {fmt(e.raw[0])} </span>}
                {VERDICT[e.verdict] ?? e.verdict}
                {e.text ? t("：「{text}」", { text: e.text }) : ""}
                <span className="muted"> · {t("{s} 秒", { s: e.seconds })}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
      {mode === "talk" && (
        <TalkBox
          label={t("告诉 LACUNA 这条规则要怎么改")}
          placeholder={t("比如：只针对 Pei / 别那么绝对 / 直接写你想要的说法")}
          onMic={pauseMain}
          onCancel={() => setMode("view")}
          onSend={async (text) => {
            onChange(await lessonsApi.revise(epId, x.id, text));
            setMode("view");
          }}
        />
      )}
      {mode === "view" && x.state === "draft" && (
        <div className="row gap8 wrap lesson-actions">
          <button type="button" className="btn btn-primary" disabled={!!busy} onClick={() => act("adopt", () => lessonsApi.decide(epId, x.id, "adopt"))}>
            <BusyLabel busy={busy === "adopt"} label={t("采用")} />
          </button>
          <button type="button" className="btn btn-outline" disabled={!!busy} onClick={() => { setDraft(x.title); setMode("edit"); }}>
            {t("直接改")}
          </button>
          <button type="button" className="btn btn-outline" disabled={!!busy} onClick={() => setMode("talk")}>
            {t("跟 LACUNA 说怎么改")}
          </button>
          <button type="button" className="btn btn-outline" disabled={!!busy} onClick={() => act("skip", () => lessonsApi.decide(epId, x.id, "skip"))}>
            <BusyLabel busy={busy === "skip"} label={t("跳过")} />
          </button>
        </div>
      )}
      {x.state === "skipped" && (
        <div className="row gap8 wrap lesson-actions">
          <button type="button" className="btn btn-outline" disabled={!!busy} onClick={() => act("reopen", () => lessonsApi.decide(epId, x.id, "reopen"))}>
            <BusyLabel busy={busy === "reopen"} label={t("重新考虑")} />
          </button>
        </div>
      )}
      {x.state === "adopted" && (
        <p className="small muted">
          {t("从下一期的 AI 初剪开始照做。")} <a href="#/learning">{t("想撤回去「学到的规则」")}</a>
        </p>
      )}
      {err && <p className="small error">{err}</p>}
    </li>
  );
}
