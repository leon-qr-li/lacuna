import { forwardRef, useImperativeHandle, useLayoutEffect, useRef } from "react";
import type { TextareaHTMLAttributes } from "react";

type Props = Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "onChange" | "value"> & {
  value: string;
  onChange: (v: string) => void;
  /** Enter (no Shift, not mid-IME) sends. Defaults to submitting the surrounding form. */
  onEnter?: () => void;
  maxRows?: number;
};

/** A text box for sentences: grows with what you type (up to maxRows), Enter sends, Shift+Enter is a new line. */
export const GrowText = forwardRef<HTMLTextAreaElement, Props>(function GrowText(
  { value, onChange, onEnter, maxRows = 6, className, rows = 1, ...rest },
  ref,
) {
  const el = useRef<HTMLTextAreaElement>(null);
  useImperativeHandle(ref, () => el.current!);
  useLayoutEffect(() => {
    const t = el.current;
    if (!t) return;
    t.style.height = "auto";
    const line = parseFloat(getComputedStyle(t).lineHeight) || 22;
    t.style.height = `${Math.min(t.scrollHeight, line * maxRows + 24)}px`;
  }, [value, maxRows]);
  return (
    <textarea
      ref={el}
      rows={rows}
      className={`grow-text ${className ?? ""}`}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onKeyDown={(e) => {
        if (e.key !== "Enter" || e.shiftKey || e.nativeEvent.isComposing) return;
        e.preventDefault();
        if (onEnter) onEnter();
        else e.currentTarget.form?.requestSubmit();
      }}
      {...rest}
    />
  );
});
