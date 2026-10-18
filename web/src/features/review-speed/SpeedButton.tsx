import { t } from "../../i18n";
import { nextRate, rateLabel } from "./speed";
import "./review-speed.css";

/** Speed chip (review dock, music page player): each tap (or S in review) steps 1× → 1.25× → 1.5× → 2× → 1×. */
export function SpeedButton({ rate, onChange, testId = "review-speed", hint = t("播放速度（S 切换）") }: {
  rate: number;
  onChange: (r: number) => void;
  testId?: string;
  hint?: string;
}) {
  return (
    <button
      type="button"
      className={`rs-btn ${rate !== 1 ? "is-on" : ""}`}
      data-testid={testId}
      aria-label={t("播放速度 {rate}", { rate: rateLabel(rate) })}
      title={hint}
      onClick={() => onChange(nextRate(rate))}
    >
      {rateLabel(rate)}
    </button>
  );
}
