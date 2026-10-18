import { useEffect, useRef, useState } from "react";
import { api, type DictationContext } from "../api";
import { t } from "../i18n";
import { BusyLabel } from "../features/loading/Loading";

const MAX_S = 120; // stop on its own after two minutes

interface Props {
  available: boolean; // local recogniser ready (from /api/health)
  note?: string; // why not, if not
  disabled?: boolean;
  onStart: () => void; // e.g. pause the episode so the speakers don't talk into the mic
  onText: (text: string) => void;
  onError: (msg: string) => void;
  context?: () => DictationContext; // episode / playhead, read when recording stops
}

/** Click to talk, click again to stop: the clip is transcribed on this machine, names and homophones
 * are fixed from the episode context (text only), and the text lands in the box for Leon to read
 * before sending. Audio is never sent anywhere else. */
export function MicButton({ available, note, disabled, onStart, onText, onError, context }: Props) {
  const [state, setState] = useState<"idle" | "starting" | "recording" | "busy">("idle");
  const [secs, setSecs] = useState(0);
  const rec = useRef<MediaRecorder | null>(null);
  const timer = useRef<number | null>(null);
  const supported = typeof window !== "undefined" && !!navigator.mediaDevices?.getUserMedia && "MediaRecorder" in window;

  const clearTimer = () => {
    if (timer.current !== null) window.clearInterval(timer.current);
    timer.current = null;
  };
  useEffect(
    () => () => {
      clearTimer();
      rec.current?.stream.getTracks().forEach((t) => t.stop());
    },
    [],
  );

  const start = async () => {
    setState("starting");
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
    } catch (err) {
      setState("idle");
      const name = (err as DOMException).name;
      onError(
        name === "NotAllowedError" || name === "SecurityError"
          ? t("浏览器没允许用麦克风：点地址栏左边的图标，把麦克风改成「允许」再试")
          : name === "NotFoundError"
            ? t("没找到麦克风，插上再试")
            : t("打不开麦克风：{message}", { message: (err as Error).message }),
      );
      return;
    }
    onStart();
    api.dictationWarm().catch(() => {}); // load the model while Leon talks
    const chunks: Blob[] = [];
    const r = new MediaRecorder(stream);
    rec.current = r;
    r.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    r.onstop = async () => {
      clearTimer();
      stream.getTracks().forEach((t) => t.stop());
      rec.current = null;
      setState("busy");
      try {
        const out = await api.dictate(new Blob(chunks, { type: r.mimeType }), context?.() ?? {});
        if (out.text) onText(out.text);
        else onError(t("没听清，再说一次试试"));
      } catch (err) {
        onError(t("语音识别失败：{message}", { message: (err as Error).message }));
      } finally {
        setState("idle");
      }
    };
    r.start(250);
    setSecs(0);
    const t0 = Date.now();
    timer.current = window.setInterval(() => {
      const s = (Date.now() - t0) / 1000;
      setSecs(Math.floor(s));
      if (s >= MAX_S && r.state === "recording") r.stop();
    }, 250);
    setState("recording");
  };

  const click = () => {
    if (state === "idle") void start();
    else if (state === "recording") rec.current?.stop();
  };

  const can = supported && available;
  const title = !supported
    ? t("这个浏览器不支持录音")
    : !available
      ? t("语音输入暂不可用：{p0}", { p0: note ?? "" })
      : state === "recording"
        ? t("再点一下结束，识别成文字")
        : t("点一下开始说话（在本机识别，声音不上传）");
  const label =
    state === "recording"
      ? `● ${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}`
      : state === "busy"
        ? <BusyLabel busy label={t("识别中…")} />
        : "🎤";
  return (
    <button
      type="button"
      className={`btn mic ${state === "recording" ? "mic-on" : ""}`}
      onClick={click}
      disabled={!can || disabled || state === "starting" || state === "busy"}
      title={title}
      aria-label={state === "recording" ? t("结束录音") : t("语音输入")}
      aria-pressed={state === "recording"}
      data-testid="mic"
    >
      {label}
    </button>
  );
}
