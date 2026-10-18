import { useState } from "react";
import type { ReactNode } from "react";
import { GrowText } from "./GrowText";
import { MicButton } from "./MicButton";
import "./PromptBar.css";

interface Props {
  label: string; // accessible name of the text box
  placeholder: string;
  submitLabel: string; // e.g. 改
  hint?: ReactNode; // small text left of the buttons, e.g. "Enter 发送"
  disabled?: boolean;
  /** Voice input (local recogniser); leave out to hide the mic. */
  mic?: { available: boolean; note?: string; onStart: () => void; onError: (msg: string) => void };
  /** Resolves true when the text was taken (the box then empties). */
  onSubmit: (text: string) => Promise<boolean> | boolean;
  testId?: string;
}

const MicIcon = () => (
  <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <rect x="9" y="3" width="6" height="11" rx="3" />
    <path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21" />
  </svg>
);

const SendIcon = () => (
  <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 19V5M6 11l6-6 6 6" />
  </svg>
);

/** One input bar for "say it in a sentence" boxes: a wide text box that grows with what you type,
 *  with voice input and the send button inside the same frame (Enter sends, Shift+Enter is a new line). */
export function PromptBar({ label, placeholder, submitLabel, hint, disabled, mic, onSubmit, testId }: Props) {
  const [text, setText] = useState("");
  const send = async () => {
    const v = text.trim();
    if (v && (await onSubmit(v))) setText("");
  };
  return (
    <form
      className={`prompt-bar${disabled ? " is-disabled" : ""}`}
      data-testid={testId}
      onSubmit={(e) => {
        e.preventDefault();
        void send();
      }}
    >
      <GrowText className="prompt-input" aria-label={label} placeholder={placeholder} value={text} onChange={setText} disabled={disabled} maxRows={5} />
      <div className="prompt-foot">
        {hint && <span className="prompt-hint">{hint}</span>}
        <span className="grow" />
        {mic && (
          <MicButton
            available={mic.available}
            note={mic.note}
            disabled={disabled}
            onStart={mic.onStart}
            onText={(said) => setText((cur) => (cur.trim() ? `${cur.trimEnd()} ${said}` : said))}
            onError={mic.onError}
            idleIcon={<MicIcon />}
          />
        )}
        <button type="submit" className="btn prompt-send" disabled={disabled || !text.trim()}>
          <SendIcon />
          <span>{submitLabel}</span>
        </button>
      </div>
    </form>
  );
}
