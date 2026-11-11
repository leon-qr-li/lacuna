// 测速 (batch 7, S1), on 存储与保留: the server sends a 200 MB test file to the cloud storage and back
// (lacuna_app/speedtest.py), then deletes it. Only the site owner presses it.
import { useEffect, useState } from "react";
import { api } from "../api";
import { t } from "../i18n";
import { act, ago, fmtBytes, isDemo } from "../ui";

interface Speed {
  state: "idle" | "running" | "done" | "error";
  stage?: "upload" | "download" | null;
  size?: number;
  upload_s?: number;
  download_s?: number;
  upload_mbps?: number;
  download_mbps?: number;
  finished?: number;
  error?: string;
}

export function SpeedTest() {
  const [s, setS] = useState<Speed>({ state: "idle" });
  const running = s.state === "running";
  useEffect(() => {
    if (isDemo()) return;
    api<Speed>("GET", "/api/admin/storage/speed").then(setS, () => undefined);
  }, []);
  useEffect(() => {
    if (!running) return;
    const k = window.setInterval(() => api<Speed>("GET", "/api/admin/storage/speed").then(setS, () => undefined), 1500);
    return () => window.clearInterval(k);
  }, [running]);
  const start = async () => {
    const out = await act(() => api<Speed>("POST", "/api/admin/storage/speed"));
    if (out) setS(out);
  };
  return (
    <div className="a-speed" data-testid="speedtest">
      <div className="a-row wrap">
        <button type="button" className="a-btn" onClick={() => void start()} disabled={running} data-testid="speedtest-start">
          {running ? (s.stage === "download" ? t("正在取回…") : t("正在上传…")) : t("测速")}
        </button>
        <span className="a-muted small">{t("传一个 {size} 的测试文件到云存储再取回来，测完自动删掉，大约 1–3 分钟。", { size: fmtBytes(s.size ?? 200 * 1024 * 1024) })}</span>
      </div>
      {s.state === "done" && (
        <p className="small" data-testid="speedtest-result">
          {t("上传 {up} 秒（{upm} Mbps），取回 {down} 秒（{downm} Mbps）", {
            up: s.upload_s ?? 0,
            upm: s.upload_mbps ?? 0,
            down: s.download_s ?? 0,
            downm: s.download_mbps ?? 0,
          })}
          {s.finished ? <span className="a-muted"> · {ago(s.finished)}</span> : null}
        </p>
      )}
      {s.state === "error" && <p className="small a-bad-text">{s.error}</p>}
    </div>
  );
}
