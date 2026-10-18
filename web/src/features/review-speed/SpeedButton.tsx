import { t } from "../../i18n";
import { nextRate, rateLabel } from "./speed";
import "./review-speed.css";

/** Speed chip in the review dock: each tap (or S) steps 1× → 1.25× → 1.5× → 2× → 1×. */
export function SpeedButton({ rate, onChange }: { rate: number; onChange: (r: number) => void }) {
  return (
    <button
      type="button"
      className={`rs-btn ${rate !== 1 ? "is-on" : ""}`}
      data-testid="review-speed"
      aria-label={t("播放速度 {rate}", { rate: rateLabel(rate) })}
      title={t("播放速度（S 切换）")}
      onClick={() => onChange(nextRate(rate))}
    >
      {rateLabel(rate)}
    </button>
  );
}
