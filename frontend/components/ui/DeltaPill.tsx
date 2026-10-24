import { Pill } from "@/components/ui/Pill";
import { deltaPolarity, formatDelta } from "@/lib/metric-format";
import type { MetricKey } from "@/lib/types";

const WORD = { improvement: "better", regression: "worse", unchanged: "same" } as const;
const TONE = { improvement: "positive", regression: "negative", unchanged: "neutral" } as const;

/**
 * Signed change with its meaning spelled out. Colour, an arrow and a word all
 * say whether the change is good for this metric, so none of them is relied on
 * alone: +24.7 safety is better, +24.7 heat stress is worse.
 */
export function DeltaPill({
  metricKey,
  delta,
  title,
  compact = false,
}: {
  metricKey: MetricKey;
  delta: number;
  title?: string;
  /** Hide the word on very narrow tiles; the arrow and colour remain. */
  compact?: boolean;
}) {
  const polarity = deltaPolarity(metricKey, delta);
  const arrow = polarity === "unchanged" ? "–" : delta > 0 ? "↑" : "↓";
  return (
    <Pill tone={TONE[polarity]} title={title} className="tabular whitespace-nowrap">
      <span aria-hidden>{arrow}</span>
      {formatDelta(metricKey, delta)}
      <span className={compact ? "sr-only" : undefined}>{WORD[polarity]}</span>
    </Pill>
  );
}
