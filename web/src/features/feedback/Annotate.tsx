import { useEffect, useRef, useState } from "react";
import { t } from "../../i18n";
import { load } from "./shot";

/** 在图上圈出来: draw on the screenshot with the mouse or a finger; 完成 gives the marked picture back. */
export function Annotate({ src, onDone, onCancel }: { src: string; onDone: (url: string) => void; onCancel: () => void }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const base = useRef<HTMLImageElement | null>(null);
  const drawing = useRef(false);
  const [marks, setMarks] = useState(0);

  const paint = () => {
    const c = canvas.current;
    if (!c || !base.current) return;
    c.width = base.current.naturalWidth;
    c.height = base.current.naturalHeight;
    c.getContext("2d")!.drawImage(base.current, 0, 0);
  };
  useEffect(() => {
    load(src).then((img) => {
      base.current = img;
      paint();
    }, onCancel);
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onCancel();
      }
    };
    window.addEventListener("keydown", key, true);
    return () => window.removeEventListener("keydown", key, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src]);

  const at = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const c = canvas.current!;
    const r = c.getBoundingClientRect();
    return [((e.clientX - r.left) * c.width) / r.width, ((e.clientY - r.top) * c.height) / r.height] as const;
  };
  const down = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const ctx = canvas.current!.getContext("2d")!;
    drawing.current = true;
    canvas.current!.setPointerCapture(e.pointerId);
    ctx.strokeStyle = "#ff3b47";
    ctx.lineWidth = Math.max(4, canvas.current!.width / 260);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.beginPath();
    ctx.moveTo(...at(e));
  };
  const move = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drawing.current) return;
    const ctx = canvas.current!.getContext("2d")!;
    ctx.lineTo(...at(e));
    ctx.stroke();
  };
  const up = () => {
    if (drawing.current) setMarks((n) => n + 1);
    drawing.current = false;
  };

  return (
    <div className="fb-annotate" role="dialog" aria-modal="true" aria-label={t("在图上圈出来")} data-testid="feedback-annotate">
      <div className="fb-annotate-bar">
        <b>{t("在图上圈出问题的地方")}</b>
        <span className="muted small">{t("按住鼠标画圈或画线")}</span>
        <span className="grow" />
        <button type="button" className="btn btn-outline btn-small" onClick={() => { paint(); setMarks(0); }} disabled={!marks}>
          {t("清除")}
        </button>
        <button type="button" className="btn btn-outline btn-small" onClick={onCancel}>
          {t("取消")}
        </button>
        <button type="button" className="btn btn-primary btn-small" onClick={() => onDone(canvas.current!.toDataURL("image/jpeg", 0.85))} data-testid="feedback-annotate-done">
          {t("完成")}
        </button>
      </div>
      <canvas ref={canvas} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up} data-testid="feedback-annotate-canvas" />
    </div>
  );
}
