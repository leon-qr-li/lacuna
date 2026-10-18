// A small box to tell LACUNA how to change a rule (typed or by voice); used by the 「记住」 card and 本集学到的规则.
import { useEffect, useRef, useState } from "react";
import type { Health } from "../../api";
import { api } from "../../api";
import { GrowText } from "../../components/GrowText";
import { MicButton } from "../../components/MicButton";
import { t } from "../../i18n";
import { BusyLabel } from "../loading/Loading";

let health: Promise<Health> | null = null;

export function TalkBox({
  placeholder,
  label,
  onSend,
  onCancel,
  onMic,
}: {
  placeholder: string;
  label: string;
  onSend: (text: string) => Promise<void>;
  onCancel: () => void;
  onMic?: () => void;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [h, setH] = useState<Health | null>(null);
  const box = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    (health ??= api.health()).then(setH).catch(() => (health = null));
    box.current?.focus();
  }, []);

  const send = async () => {
    const said = text.trim();
    if (!said || busy) return;
    setBusy(true);
    setErr(null);
    try {
      await onSend(said);
      setText("");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="talkbox" role="group" aria-label={label}>
      <GrowText
        ref={box}
        value={text}
        onChange={setText}
        onEnter={send}
        placeholder={placeholder}
        aria-label={label}
        disabled={busy}
        maxRows={4}
      />
      <div className="row gap8 wrap talkbox-row">
        <MicButton
          available={!!h?.dictation}
          note={h?.dictation_note}
          disabled={busy}
          onStart={() => onMic?.()}
          onText={(s) => {
            setText((cur) => (cur.trim() ? `${cur.trimEnd()} ${s}` : s));
            box.current?.focus();
          }}
          onError={setErr}
        />
        <span className="grow" />
        <button type="button" className="btn btn-outline" onClick={onCancel} disabled={busy}>
          {t("取消")}
        </button>
        <button type="button" className="btn btn-primary" onClick={send} disabled={busy || !text.trim()}>
          <BusyLabel busy={busy} label={t("发给 LACUNA")} busyLabel={t("LACUNA 正在改…")} />
        </button>
      </div>
      {err && <p className="small error">{err}</p>}
    </div>
  );
}
