import { useEffect, useRef, useState } from "react";
import { GrowText } from "./GrowText";
import type { AB, Episode, Health, Proposal, Usage } from "../api";
import { api, fmt } from "../api";
import { ABPlayer } from "./ABPlayer";
import { MicButton } from "./MicButton";
import { t } from "../i18n";
import { Waiting } from "../features/loading/Loading";
import { RememberButton, type Ask } from "../features/learning/RememberButton";
import { RememberCard } from "../features/lessons/RememberCard";
import type { RememberDraft, RememberReply } from "../features/lessons/api";

interface Msg {
  id: number;
  role: "ai" | "user";
  text: string;
  notes?: string[];
  usage?: Usage | null;
  at?: number;
  proposal?: Proposal;
  pstate?: "pending" | "approved" | "discarded";
  remember?: RememberDraft; // 「记住」: LACUNA's reading, confirmed in the card
}

interface Props {
  ep: Episode;
  time: number;
  onEpisode: (ep: Episode) => void;
  onPauseMain: () => void;
}

let nextId = 1;

export function ChatPanel({ ep, time, onEpisode, onPauseMain }: Props) {
  const [msgs, setMsgs] = useState<Msg[]>(() => [
    {
      id: nextId++,
      role: "ai",
      text:
        (ep.demo
          ? t("第一刀（演示）做好了：{raw} → {cut}。", { raw: fmt(ep.raw_duration), cut: fmt(ep.duration) })
          : t("第一刀做好了：{raw} → {cut}。", { raw: fmt(ep.raw_duration), cut: fmt(ep.duration) })) +
        t("有 {n} 处删得比较多或者动了插话，排在「改动审阅」最前面。", { n: ep.pending_review }) +
        t("听到哪里不对，暂停后直接跟我说。"),
    },
  ]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [abs, setAbs] = useState<Record<string, AB | "loading">>({});
  const [health, setHealth] = useState<Health | null>(null);
  const [hint, setHint] = useState(t("比如：停顿短一点 / 恢复这处 / 删掉这句"));
  const claude = health?.editor === "claude";
  const input = useRef<HTMLTextAreaElement>(null);
  const log = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .health()
      .then((h) => {
        setHealth(h);
        if (h.editor === "claude") setHint(t("比如：这段跑题了删掉 / 停顿短一点 / 把刚才删的那句恢复"));
        else push({ role: "ai", text: t("现在用的是演示规则（{editor_note}），只听得懂几种固定说法。", { editor_note: h.editor_note }) });
      })
      .catch(() => {
        /* the chat still works; the badge just stays unknown */
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const push = (m: Omit<Msg, "id">) => {
    setMsgs((ms) => [...ms, { ...m, id: nextId++ }]);
    requestAnimationFrame(() => log.current?.scrollTo({ top: log.current.scrollHeight, behavior: "smooth" }));
  };
  const setP = (pid: string, pstate: Msg["pstate"]) =>
    setMsgs((ms) => ms.map((m) => (m.proposal?.id === pid ? { ...m, pstate } : m)));

  const send = (e: React.FormEvent) => {
    e.preventDefault();
    run((said, at) => api.chat(ep.id, said, at));
  };

  const run = async (ask: Ask) => {
    const said = text.trim();
    if (!said || busy) return;
    const at = time;
    setMsgs((ms) => ms.map((m) => (m.pstate === "pending" ? { ...m, pstate: "discarded" } : m)));
    push({ role: "user", text: said, at });
    setText("");
    setBusy(true);
    try {
      const r = await ask(said, at);
      push({
        role: "ai",
        text: r.reply,
        notes: r.notes,
        usage: r.usage,
        proposal: r.proposal ?? undefined,
        pstate: r.proposal ? "pending" : undefined,
        remember: (r as RememberReply).remember,
      });
      onEpisode(await api.episode(ep.id));
    } catch (err) {
      push({ role: "ai", text: t("出错了：{message}", { message: (err as Error).message }) });
    } finally {
      setBusy(false);
    }
  };

  const preview = async (p: Proposal) => {
    setAbs((a) => ({ ...a, [p.id]: "loading" }));
    try {
      const ab = await api.proposalAB(ep.id, p.id);
      setAbs((a) => ({ ...a, [p.id]: ab }));
    } catch (err) {
      setAbs((a) => {
        const { [p.id]: _drop, ...rest } = a;
        return rest;
      });
      push({ role: "ai", text: t("试听渲染失败：{message}", { message: (err as Error).message }) });
    }
  };

  const approve = async (p: Proposal) => {
    try {
      onEpisode(await api.approve(ep.id, p.id, time));
      setP(p.id, "approved");
    } catch (err) {
      push({ role: "ai", text: t("没能应用：{message}", { message: (err as Error).message }) });
    }
  };

  const again = async (p: Proposal) => {
    try {
      onEpisode(await api.discard(ep.id, p.id, time));
    } catch {
      /* already gone */
    }
    setP(p.id, "discarded");
    setHint(t("说说要怎么改，比如：再短一点 / 只删后半句"));
    input.current?.focus();
  };

  return (
    <section className="chat" aria-label={t("AI 制作人对话")}>
      <h2 className="chat-title">
        {t("AI 制作人")}{" "}
        {health && (
          <span
            className={`chip small ${claude ? "chip-ok" : ""}`}
            data-testid="editor-badge"
            title={claude ? t("接的是 Claude API（只发送逐字稿和数字，不发送音频）") : health.editor_note}
          >
            {claude ? "Claude" : t("演示规则")}
          </span>
        )}
      </h2>
      <div className="chat-log" ref={log} aria-live="polite" data-testid="chat-log">
        {msgs.map((m) => (
          <div key={m.id} className={`msg msg-${m.role}`}>
            {m.at !== undefined && <span className="at mono">@ {fmt(m.at)}</span>}
            <div>{m.text}</div>
            {m.notes?.map((n, i) => (
              <div key={i} className="note small">
                {n}
              </div>
            ))}
            {m.usage && (
              <div className="meta muted small mono" data-testid="usage">
                Claude · {t("{s} 秒 · ≈${cost}", { s: m.usage.seconds.toFixed(1), cost: m.usage.cost_usd.toFixed(3) })}
              </div>
            )}
            {m.remember && <RememberCard epId={ep.id} draft={m.remember} onPauseMain={onPauseMain} />}
            {m.proposal && (
              <ProposalCard
                p={m.proposal}
                state={m.pstate ?? "pending"}
                ab={abs[m.proposal.id]}
                onPreview={() => preview(m.proposal!)}
                onApprove={() => approve(m.proposal!)}
                onAgain={() => again(m.proposal!)}
                onPlay={onPauseMain}
              />
            )}
          </div>
        ))}
        {busy && <Waiting className="msg msg-ai" label={claude ? t("Claude 正在看这附近的逐字稿…") : t("正在看这附近…")} />}
      </div>
      <form className="chat-form" onSubmit={send}>
        <label htmlFor="say" className="sr-only">
          {t("对 AI 制作人说（锚定在当前播放位置）")}
        </label>
        <GrowText
          id="say"
          ref={input}
          value={text}
          placeholder={hint}
          onChange={setText}
          autoComplete="off"
        />
        <div className="chat-form-row">
          <span className="at-chip mono" title={t("指令锚定在当前播放位置")}>
            @ {fmt(time)}
          </span>
          <span className="grow" />
          <MicButton
            available={!!health?.dictation}
            note={health?.dictation_note}
            disabled={busy}
            onStart={onPauseMain}
            onText={(t) => {
              setText((cur) => (cur.trim() ? `${cur.trimEnd()} ${t}` : t));
              input.current?.focus();
            }}
            onError={(msg) => push({ role: "ai", text: msg })}
            context={() => ({ episode: ep.id, at: time, where: "chat" })}
          />
          <RememberButton epId={ep.id} disabled={busy || !text.trim()} onSend={run} />
          <button type="submit" className="btn btn-primary" disabled={busy || !text.trim()}>
            {t("发送")}
          </button>
        </div>
      </form>
    </section>
  );
}

function ProposalCard({
  p,
  state,
  ab,
  onPreview,
  onApprove,
  onAgain,
  onPlay,
}: {
  p: Proposal;
  state: string;
  ab: AB | "loading" | undefined;
  onPreview: () => void;
  onApprove: () => void;
  onAgain: () => void;
  onPlay: () => void;
}) {
  if (state === "approved") return <div className="pstate ok">{t("✓ 已批准并应用：{title}", { title: p.title })}</div>;
  if (state === "discarded") return <div className="pstate muted">{t("已放弃这个建议")}</div>;
  return (
    <div className="proposal" data-testid="proposal">
      <div className="row wrap gap8">
        {!ab && (
          <button type="button" className="btn btn-outline-accent" onClick={onPreview}>
            {t("试听前后对比")}
          </button>
        )}
        <button type="button" className="btn btn-primary" onClick={onApprove}>
          {t("批准")}
        </button>
        <button type="button" className="btn btn-outline" onClick={onAgain}>
          {t("再改")}
        </button>
      </div>
      {ab && (
        <ABPlayer
          ab={ab === "loading" ? null : ab}
          loading={ab === "loading"}
          labels={[t("现在"), t("改后")]}
          onPlay={onPlay}
        />
      )}
    </div>
  );
}
