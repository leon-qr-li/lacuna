import { useEffect, useRef, useState } from "react";
import { api, type Health } from "../../api";
import { MicButton } from "../../components/MicButton";
import { lang, t } from "../../i18n";
import { BusyLabel } from "../loading/Loading";
import { Annotate } from "./Annotate";
import { feedbackApi, type Context, type Importance, type Kind } from "./api";
import { onOpenFeedback, type Prefill } from "./bus";
import { MyFeedback } from "./MyFeedback";
import { captureApp, fromFile } from "./shot";
import { lastFailure, trail } from "./trail";
import { setUnread, useStaff, useUnread } from "./unread";

const KINDS: { id: Kind; label: string }[] = [
  { id: "bug", label: t("遇到问题") },
  { id: "idea", label: t("我有个想法") },
  { id: "praise", label: t("夸一句") },
];
const IMPORTANCE: { id: Importance; label: string }[] = [
  { id: "nice", label: t("有了更好") },
  { id: "need", label: t("很需要") },
  { id: "fine", label: t("没有就不用") },
];

const clockText = (s: number) => {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  return `${h ? `${h}:` : ""}${String(m).padStart(h ? 2 : 1, "0")}:${String(sec).padStart(2, "0")}`;
};

/** Where the person is, read when the panel opens (before it covers anything). */
function where(p: Prefill): Context {
  const ep = /^#\/ep\/([^/]+)/.exec(location.hash)?.[1];
  const audio = document.querySelector("audio");
  const title = document.querySelector(".topbar .ep-title")?.textContent?.trim();
  const step = document.querySelector(".topbar [aria-current='page'], .steps [aria-current], .step.on")?.textContent?.trim();
  return {
    page: location.hash || "#/",
    title: [title, step].filter(Boolean).join(" · ") || undefined,
    episode: ep ? decodeURIComponent(ep) : undefined,
    at: ep && audio && audio.currentTime > 0 ? Math.round(audio.currentTime) : undefined,
    lang,
    error: p.error ? [p.error.title, p.error.message].filter(Boolean).join(" · ") : lastFailure() ?? undefined,
    error_code: p.error?.code,
    actions: trail(),
  };
}

/**
 * The 反馈 panel (design A1–A4, A8): a side panel over the page. One mounted copy for the whole app
 * (index.tsx), opened by `openFeedback()`. 遇到问题 takes a picture of the page as it was when the panel opened.
 */
export function FeedbackHost() {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<"write" | "mine">("write");
  const [pre, setPre] = useState<Prefill>({});
  const [ctx, setCtx] = useState<Context>({});
  const [kind, setKind] = useState<Kind>("bug");
  const [text, setText] = useState("");
  const [importance, setImportance] = useState<Importance | null>(null);
  const [quoteOk, setQuoteOk] = useState(false);
  const [attachPage, setAttachPage] = useState(true);
  const [shot, setShot] = useState<string | null>(null);
  const [useShot, setUseShot] = useState(true);
  const [shooting, setShooting] = useState(false);
  const [marking, setMarking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [sent, setSent] = useState<Kind | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const unread = useUnread(false);
  const staff = useStaff();
  const file = useRef<HTMLInputElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);

  useEffect(
    () =>
      onOpenFeedback(async (p) => {
        if (open) {
          if (p.mine) setTab("mine");
          return;
        }
        // the picture first, while nothing of ours is over the page
        setCtx(where(p));
        setPre(p);
        setKind(p.kind ?? (p.source === "publish" ? "idea" : "bug"));
        setText("");
        setImportance(null);
        setQuoteOk(false);
        setAttachPage(true);
        setUseShot(true);
        setErr(null);
        setSent(null);
        setTab(p.mine ? "mine" : "write");
        setShot(null);
        setShooting(true);
        setOpen(true);
        const pic = await captureApp();
        setShot(pic);
        setShooting(false);
      }),
    [open],
  );
  useEffect(() => {
    if (!open) return;
    if (!health) api.health().then(setHealth, () => undefined);
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !marking) setOpen(false);
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [open, marking, health]);
  useEffect(() => {
    if (open && tab === "write" && !sent) box.current?.focus();
  }, [open, tab, kind, sent]);

  if (!open) return null;

  const fromError = pre.source === "error" && !!pre.error;
  const fromPublish = pre.source === "publish";
  const canSend = !busy && (text.trim().length > 0 || fromError);

  const send = async () => {
    setBusy(true);
    setErr(null);
    try {
      const context: Context = kind === "bug" || attachPage ? ctx : { lang };
      const r = await feedbackApi.send({
        kind,
        text: text.trim(),
        source: pre.source ?? "button",
        context,
        importance: kind === "idea" ? importance ?? undefined : undefined,
        quote_ok: kind === "praise" ? quoteOk : undefined,
        platforms: pre.platforms,
        shot: kind === "bug" && useShot && shot ? shot : undefined,
      });
      setUnread(r.unread);
      setSent(kind);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const label =
    fromError ? t("还想补充什么吗？（可以不写）")
    : fromPublish && kind === "idea" ? t("你希望发布这一步怎么做？")
    : kind === "bug" ? t("发生了什么？")
    : kind === "idea" ? t("你希望 LACUNA 能做什么？")
    : t("哪里让你觉得好用？");
  const placeholder =
    kind === "bug" ? t("比如：导出到一半卡住了，进度条一直停在 80%。")
    : kind === "idea" ? t("比如：希望能直接发到我用的托管平台。")
    : t("比如：口癖去得很干净，说话的感觉一点没变。");

  return (
    <div className="fb-host" data-testid="feedback-host">
      <div className="fb-scrim" onMouseDown={() => setOpen(false)} />
      <aside className="fb-panel" role="dialog" aria-modal="true" aria-labelledby="fb-title" data-testid="feedback-panel">
        <header className="fb-head">
          <h2 id="fb-title">{t("反馈")}</h2>
          <span className="grow" />
          <div className="fb-tabs" role="tablist">
            <button type="button" role="tab" aria-selected={tab === "write"} className={tab === "write" ? "on" : ""} onClick={() => { setTab("write"); setSent(null); }}>
              {t("写反馈")}
            </button>
            <button type="button" role="tab" aria-selected={tab === "mine"} className={tab === "mine" ? "on" : ""} onClick={() => setTab("mine")} data-testid="feedback-tab-mine">
              {t("我的反馈")}
              {unread > 0 && <span className="fb-dot" aria-label={t("有新回复")} />}
            </button>
          </div>
          <button type="button" className="btn btn-ghost btn-small fb-close" onClick={() => setOpen(false)} aria-label={t("关闭")}>
            ✕
          </button>
        </header>

        {tab === "mine" ? (
          <div className="fb-body">
            <MyFeedback onWrite={() => setTab("write")} />
            {staff && (
              <a className="small fb-all-link" href="#/feedback-all" onClick={() => setOpen(false)} data-testid="feedback-all-link">
                {t("全部反馈（临时）")} →
              </a>
            )}
          </div>
        ) : sent ? (
          <div className="fb-body fb-sent" data-testid="feedback-sent">
            <div className="fb-sent-mark" aria-hidden="true">✓</div>
            <h3>{t("收到了，谢谢你")}</h3>
            <p className="muted">{t("站长会亲自看每一条。处理进度和回复会出现在「我的反馈」里，也会发邮件告诉你。")}</p>
            {sent !== "praise" && (
              <p className="fb-gift">
                {t("你的反馈如果被采纳，本月送你 {n} 小时剪辑时长。", { n: 1 })}
              </p>
            )}
            <div className="row gap8">
              <button type="button" className="btn btn-outline" onClick={() => setTab("mine")}>
                {t("看我的反馈")}
              </button>
              <button type="button" className="btn btn-primary" onClick={() => setOpen(false)} data-testid="feedback-done">
                {t("完成")}
              </button>
            </div>
          </div>
        ) : (
          <form
            className="fb-body"
            onSubmit={(e) => {
              e.preventDefault();
              if (canSend) void send();
            }}
          >
            {fromError && (
              <div className="fb-prefill" data-testid="feedback-prefill">
                <span className="chip">{t("已帮你填好")}</span>
                <b>{pre.error!.title}</b>
                {pre.error!.message && <span className="small muted">{pre.error!.message}</span>}
                <span className="small muted">{t("报错详情已附上")}</span>
              </div>
            )}
            {fromPublish && (
              <div className="fb-prefill" data-testid="feedback-prefill">
                <span className="chip">{t("来自：自动发布")}</span>
                {pre.platforms && pre.platforms.length > 0 && (
                  <span className="small muted">{t("你选的平台：{list}", { list: pre.platforms.join(" / ") })}</span>
                )}
              </div>
            )}
            <div className="fb-kinds" role="radiogroup" aria-label={t("反馈类型")}>
              {KINDS.map((k) => (
                <button
                  key={k.id}
                  type="button"
                  role="radio"
                  aria-checked={kind === k.id}
                  className={`fb-chip${kind === k.id ? " on" : ""}`}
                  onClick={() => setKind(k.id)}
                  data-testid={`feedback-kind-${k.id}`}
                >
                  {k.label}
                </button>
              ))}
            </div>
            <label className="fb-label" htmlFor="fb-text">
              {label}
            </label>
            <div className="fb-textwrap">
              <textarea
                id="fb-text"
                ref={box}
                className="fb-text"
                rows={5}
                maxLength={4000}
                value={text}
                placeholder={placeholder}
                onChange={(e) => setText(e.target.value)}
                data-testid="feedback-text"
              />
              <div className="fb-mic">
                <MicButton
                  available={!!health?.dictation}
                  note={health?.dictation_note}
                  onStart={() => document.querySelectorAll("audio").forEach((a) => a.pause())}
                  onText={(said) => setText((cur) => (cur.trim() ? `${cur.trimEnd()} ${said}` : said))}
                  onError={setErr}
                />
              </div>
            </div>

            {kind === "idea" && (
              <div className="fb-field">
                <span className="fb-label">{t("这对你有多重要？")}</span>
                <div className="fb-kinds">
                  {IMPORTANCE.map((x) => (
                    <button key={x.id} type="button" className={`fb-chip small${importance === x.id ? " on" : ""}`} aria-pressed={importance === x.id} onClick={() => setImportance(importance === x.id ? null : x.id)}>
                      {x.label}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {kind === "praise" && (
              <label className="fb-check" data-testid="feedback-quote">
                <input type="checkbox" checked={quoteOk} onChange={(e) => setQuoteOk(e.target.checked)} />
                <span>
                  <b>{t("同意我们公开引用这段话")}</b>
                  <br />
                  <span className="small muted">
                    {t("会用在 LACUNA 的官网和宣传里，署名只写节目名，不写你的名字。不勾选的话，这段话只有我们自己看。")}
                  </span>
                </span>
              </label>
            )}
            {kind !== "bug" && (
              <label className="fb-check">
                <input type="checkbox" checked={attachPage} onChange={(e) => setAttachPage(e.target.checked)} />
                <span className="small">{t("附上我现在所在的页面")}</span>
              </label>
            )}

            {kind === "bug" && (
              <div className="fb-shot" data-testid="feedback-shot">
                <label className="fb-check">
                  <input type="checkbox" checked={useShot && !!shot} disabled={!shot} onChange={(e) => setUseShot(e.target.checked)} data-testid="feedback-shot-use" />
                  <span>
                    <b className="small">{fromError ? t("附上截图（出错那一刻的画面）") : t("附上这张截图")}</b>
                    <br />
                    <span className="small muted">{t("只截 LACUNA 页面，不录音，只有站长能看")}</span>
                  </span>
                </label>
                <div className="fb-shot-row">
                  <div className={`fb-thumb${useShot ? "" : " off"}`}>
                    {shooting ? <span className="small muted">{t("正在截图…")}</span> : shot ? <img src={shot} alt={t("截图预览")} /> : <span className="small muted">{t("这一页没法截图，可以自己换一张")}</span>}
                  </div>
                  <div className="fb-shot-acts">
                    <button type="button" className="btn btn-outline btn-small" onClick={() => file.current?.click()}>
                      {t("换一张图")}
                    </button>
                    <button type="button" className="btn btn-outline btn-small" disabled={!shot} onClick={() => setMarking(true)} data-testid="feedback-annotate-open">
                      {t("在图上圈出来")}
                    </button>
                    <input
                      ref={file}
                      type="file"
                      accept="image/png,image/jpeg,image/webp"
                      hidden
                      onChange={async (e) => {
                        const f = e.target.files?.[0];
                        e.target.value = "";
                        if (!f) return;
                        try {
                          setShot(await fromFile(f));
                          setUseShot(true);
                        } catch {
                          setErr(t("这张图打不开，换一张试试"));
                        }
                      }}
                    />
                  </div>
                </div>
              </div>
            )}

            {(kind === "bug" || attachPage) && (
              <div className="fb-auto" data-testid="feedback-context">
                <b className="small">{t("自动附上，帮我们更快找到问题")}</b>
                <ul className="small muted">
                  <li>
                    {t("页面：{page}", { page: ctx.title || ctx.page || "—" })}
                    {ctx.at != null && ` · ${t("播放到 {time}", { time: clockText(ctx.at) })}`}
                  </li>
                  <li>{t("App 版本、浏览器、界面语言")}</li>
                  {kind === "bug" && <li>{t("最近 {n} 步操作和最近一次报错", { n: ctx.actions?.length ?? 0 })}</li>}
                  {fromPublish && <li>{t("节目和你选的平台")}</li>}
                </ul>
              </div>
            )}

            {err && <p className="error small">{err}</p>}
            <footer className="fb-foot">
              <span className="small muted">{t("站长会亲自看每一条")}</span>
              <span className="grow" />
              <button type="button" className="btn btn-outline" onClick={() => setOpen(false)}>
                {t("取消")}
              </button>
              <button type="submit" className="btn btn-primary" disabled={!canSend} data-testid="feedback-send">
                <BusyLabel busy={busy} label={t("发送")} />
              </button>
            </footer>
          </form>
        )}
      </aside>
      {marking && shot && (
        <Annotate
          src={shot}
          onCancel={() => setMarking(false)}
          onDone={(url) => {
            setShot(url);
            setUseShot(true);
            setMarking(false);
          }}
        />
      )}
    </div>
  );
}
