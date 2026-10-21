import { useState } from "react";
import { MODEL_COLOURS } from "../format";

export interface Bar {
  key: string; // unique row id (model id)
  colourKey: string; // model slot that decides the identity colour
  label: string;
  value: number | null;
  display: string;
  detail?: string;
}

interface Props {
  title: string;
  subtitle?: string;
  bars: Bar[];
  better: "lower" | "higher";
  max?: number;
  compact?: boolean;
}

// Horizontal bars, one per model (identity colour), value labels in text ink,
// best value marked with a text tag rather than colour alone.
export default function BarChart({ title, subtitle, bars, better, max, compact }: Props) {
  const [hover, setHover] = useState<string | null>(null);
  const values = bars.map((b) => b.value).filter((v): v is number => v != null);
  const top = max ?? Math.max(1e-9, ...values.map((v) => Math.abs(v)));
  const best = values.length ? (better === "lower" ? Math.min(...values) : Math.max(...values)) : null;

  return (
    <figure className={`chart ${compact ? "chart--compact" : ""}`}>
      <figcaption>
        <span className="chart__title">{title}</span>
        {subtitle && <span className="chart__sub">{subtitle}</span>}
      </figcaption>
      <div className="chart__rows" role="table" aria-label={title}>
        {bars.map((b) => {
          const w = b.value == null ? 0 : Math.max(0.6, (Math.abs(b.value) / top) * 100);
          const isBest = b.value != null && b.value === best && values.length > 1;
          return (
            <div
              key={b.key}
              className={`chart__row ${hover && hover !== b.key ? "is-dim" : ""}`}
              role="row"
              onMouseEnter={() => setHover(b.key)}
              onMouseLeave={() => setHover(null)}
            >
              <span className="chart__label" role="rowheader">
                <i style={{ background: MODEL_COLOURS[b.colourKey] }} />
                {b.label}
              </span>
              <span className="chart__track" role="cell">
                {b.value != null ? (
                  <span className="chart__bar" style={{ width: `${w}%`, background: MODEL_COLOURS[b.colourKey] }} />
                ) : (
                  <span className="chart__na">no data</span>
                )}
                <span className="chart__value">
                  {b.display}
                  {isBest && <em className="best-tag">best</em>}
                </span>
              </span>
              {hover === b.key && b.detail && <span className="chart__tip">{b.detail}</span>}
            </div>
          );
        })}
      </div>
    </figure>
  );
}
