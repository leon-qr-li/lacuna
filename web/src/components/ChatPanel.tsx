import { useRef, useState } from "react";
import type { AB, Episode, Proposal } from "../api";
import { api, fmt } from "../api";
import { ABPlayer } from "./ABPlayer";

interface Msg {
  id: number;
  role: "ai" | "user";
  text: string;
  at?: number;
  proposal?: Proposal;
  pstate?: "pending" | "approved" | "discarded";
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
        `第一刀${ep.demo ? "（演示）" : ""}做好了：${fmt(ep.raw_duration)} → ${fmt(ep.duration)}。` +
        `有 ${ep.pending_review} 处删得比较多或者动了插话，排在「改动审阅」最前面。` +
        `听到哪里不对，暂停后直接跟我说。`,
    },
  ]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [abs, setAbs] = useState<Record<string, AB | "loading">>({});
  const [hint, setHint] = useState("比如：停顿短一点 / 恢复这处 / 删掉这句");
  const input = useRef<HTMLInputElement>(null);
  const log = useRef<HTMLDivElement>(null);

  const push = (m: Omit<Msg, "id">) => {
    setMsgs((ms) => [...ms, { ...m, id: nextId++ }]);
    requestAnimationFrame(() => log.current?.scrollTo({ top: log.current.scrollHeight, behavior: "smooth" }));
  };
  const setP = (pid: string, pstate: Msg["pstate"]) =>
    setMsgs((ms) => ms.map((m) => (m.proposal?.id === pid ? { ...m, pstate } : m)));

  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    const t = text.trim();
    if (!t || busy) return;
    const at = time;
    setMsgs((ms) => ms.map((m) => (m.pstate === "pending" ? { ...m, pstate: "discarded" } : m)));
    push({ role: "user", text: t, at });
    setText("");
    setBusy(true);
    try {
      const r = await api.chat(ep.id, t, at);
      push({ role: "ai", text: r.reply, proposal: r.proposal ?? undefined, pstate: r.proposal ? "pending" : undefined });
      onEpisode(await api.episode(ep.id));
    } catch (err) {
      push({ role: "ai", text: `出错了：${(err as Error).message}` });
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
      push({ role: "ai", text: `试听渲染失败：${(err as Error).message}` });
    }
  };

  const approve = async (p: Proposal) => {
    try {
      onEpisode(await api.approve(ep.id, p.id, time));
      setP(p.id, "approved");
    } catch (err) {
      push({ role: "ai", text: `没能应用：${(err as Error).message}` });
    }
  };

  const again = async (p: Proposal) => {
    try {
      onEpisode(await api.discard(ep.id, p.id, time));
    } catch {
      /* already gone */
    }
    setP(p.id, "discarded");
    setHint("说说要怎么改，比如：再短一点 / 只删后半句");
    input.current?.focus();
  };

  return (
    <section className="chat" aria-label="AI 制作人对话">
      <h2 className="chat-title">AI 制作人</h2>
      <div className="chat-log" ref={log} aria-live="polite" data-testid="chat-log">
        {msgs.map((m) => (
          <div key={m.id} className={`msg msg-${m.role}`}>
            {m.at !== undefined && <span className="at mono">@ {fmt(m.at)}</span>}
            <div>{m.text}</div>
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
        {busy && <div className="msg msg-ai muted">正在看这附近…</div>}
      </div>
      <form className="chat-form" onSubmit={send}>
        <label htmlFor="say" className="sr-only">
          对 AI 制作人说（锚定在当前播放位置）
        </label>
        <span className="at-chip mono" title="指令锚定在当前播放位置">
          @ {fmt(time)}
        </span>
        <input
          id="say"
          ref={input}
          type="text"
          value={text}
          placeholder={hint}
          onChange={(e) => setText(e.target.value)}
          autoComplete="off"
        />
        <button type="submit" className="btn btn-primary" disabled={busy || !text.trim()}>
          发送
        </button>
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
  if (state === "approved") return <div className="pstate ok">✓ 已批准并应用：{p.title}</div>;
  if (state === "discarded") return <div className="pstate muted">已放弃这个建议</div>;
  return (
    <div className="proposal" data-testid="proposal">
      <div className="row wrap gap8">
        {!ab && (
          <button type="button" className="btn btn-outline-accent" onClick={onPreview}>
            试听前后对比
          </button>
        )}
        <button type="button" className="btn btn-primary" onClick={onApprove}>
          批准
        </button>
        <button type="button" className="btn btn-outline" onClick={onAgain}>
          再改
        </button>
      </div>
      {ab && (
        <ABPlayer
          ab={ab === "loading" ? null : ab}
          loading={ab === "loading"}
          labels={["现在", "改后"]}
          onPlay={onPlay}
        />
      )}
    </div>
  );
}
