// Suggested music (by use, or from talking to Claude): heard first, applied only when accepted
import { useState } from "react";
import type { MusicDraft } from "./api";
import { fmt } from "../../api";

export function DraftCard({ d, previewing, onPreview, onMove, onAccept, onDiscard }: {
  d: MusicDraft;
  previewing: string | null;
  onPreview: (pid: string) => void;
  onMove: (pid: string, voice_s: number) => void;
  onAccept: () => void;
  onDiscard: () => void;
}) {
  const at = (pid: string) => d.placements.find((p) => p.id === pid);
  return (
    <div className="card banner-card music-draft" data-testid="music-draft">
      <div className="row gap8 wrap baseline">
        <strong className="grow">{d.source === "auto" ? "建议的配乐" : "Claude 建议这样改"}</strong>
        <span className="small muted">成品变成 {fmt(d.duration)}</span>
      </div>
      {d.message && <p className="small">{d.message}</p>}
      <ul className="draft-changes">
        {d.changes.map((c) => {
          const p = at(c.pid);
          const alts = d.alternatives[c.pid] ?? [];
          return (
            <li key={c.pid + c.kind} className="row gap8 wrap" data-testid="draft-change">
              <span className="grow">
                {c.text}
                {p?.start_s != null && <span className="mono small"> · {fmt(p.at_s ?? p.start_s)}</span>}
              </span>
              {c.previewable && (
                <button type="button" className="btn btn-small btn-outline" aria-pressed={previewing === c.pid} onClick={() => onPreview(c.pid)}>
                  {previewing === c.pid ? "停止" : "试听"}
                </button>
              )}
              {alts.length > 0 && (
                <span className="row gap4 wrap small">
                  换个位置：
                  {alts.map((a) => (
                    <button key={a.voice_s} type="button" className="chip-select" onClick={() => onMove(c.pid, a.voice_s)}>
                      {fmt(a.final_s)}
                    </button>
                  ))}
                </span>
              )}
            </li>
          );
        })}
      </ul>
      {d.stale && <p className="error small">这条建议之后配乐又改过了，已经过期。点「不要」再重新来一次。</p>}
      <div className="row gap8">
        <button type="button" className="btn btn-primary" disabled={d.stale} onClick={onAccept}>
          采用
        </button>
        <button type="button" className="btn btn-outline" onClick={onDiscard}>
          不要
        </button>
        <span className="small muted grow">采用之前不会进导出。</span>
      </div>
    </div>
  );
}

export function MusicChatBox({ onSend }: { onSend: (text: string) => Promise<boolean> }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const send = () => {
    const t = text.trim();
    if (!t || busy) return;
    setBusy(true);
    void onSend(t).then((ok) => {
      setBusy(false);
      if (ok) setText("");
    });
  };
  return (
    <div className="card music-chat">
      <h2>跟 Claude 说配乐怎么改</h2>
      <div className="row gap8">
        <input
          className="grow"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="比如：间奏晚两秒 / 背景音小 3 dB / 片尾去掉"
          aria-label="跟 Claude 说配乐怎么改"
          disabled={busy}
        />
        <button type="button" className="btn btn-primary" onClick={send} disabled={busy || !text.trim()}>
          {busy ? "Claude 在想…" : "发送"}
        </button>
      </div>
      <p className="small muted">Claude 只看文字（配乐位置、素材名和备注、附近的对话），不听音频。改动先变成建议，试听满意再采用。</p>
    </div>
  );
}
