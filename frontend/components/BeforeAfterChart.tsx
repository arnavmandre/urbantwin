"use client";

import { Card, CardHeader } from "@/components/ui/Card";
import { Pill } from "@/components/ui/Pill";
import { cx } from "@/lib/cx";
import {
  COMPARISON_METRICS,
  METRIC_META,
  deltaPolarity,
  directionLabel,
  formatDelta,
  formatMetric,
  metricFraction,
} from "@/lib/metric-format";
import type { MetricKey, SimulationMetrics } from "@/lib/types";

/**
 * Before/after comparison.
 *
 * Both arms are drawn against the same axis for a given metric, so a bar that
 * looks shorter is shorter. Whether shorter is good is stated per row rather
 * than implied by colour alone.
 */
export function BeforeAfterChart({
  before,
  after,
  interventionLabel,
}: {
  before: SimulationMetrics;
  after?: SimulationMetrics;
  interventionLabel: string | null;
}) {
  return (
    <Card>
      <CardHeader
        eyebrow="Comparison"
        title="Before and after"
        description={
          after
            ? `Both arms use the same scale per metric. ${
                interventionLabel ?? ""
              }`.trim()
            : "No intervention arm was produced for this run, so only the current state is shown."
        }
        actions={
          <div className="flex items-center gap-3 text-[11px] text-ink-3">
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-2 w-5 rounded-full bg-ink-4" /> Before
            </span>
            {after ? (
              <span className="flex items-center gap-1.5">
                <span className="inline-block h-2 w-5 rounded-full bg-accent" /> After
              </span>
            ) : null}
          </div>
        }
      />

      <div className="mt-5 grid gap-x-8 gap-y-4 lg:grid-cols-2">
        {COMPARISON_METRICS.map((key) => (
          <ComparisonRow
            key={key}
            metricKey={key}
            beforeValue={before[key]}
            afterValue={after?.[key]}
          />
        ))}
      </div>

      <div className="mt-5 border-t border-hairline pt-4">
        <ComparisonRow
          metricKey="mean_travel_minutes"
          beforeValue={before.mean_travel_minutes}
          afterValue={after?.mean_travel_minutes}
        />
        <p className="mt-2 text-[11px] leading-relaxed text-ink-3">
          Travel time is in minutes on a 0&ndash;10 axis, not the 0&ndash;100 scale used
          by the metrics above.
        </p>
      </div>
    </Card>
  );
}

function ComparisonRow({
  metricKey,
  beforeValue,
  afterValue,
}: {
  metricKey: MetricKey;
  beforeValue: number;
  afterValue?: number;
}) {
  const meta = METRIC_META[metricKey];
  const delta = afterValue === undefined ? null : afterValue - beforeValue;
  const polarity = delta === null ? null : deltaPolarity(metricKey, delta);
  const [min, max] = meta.range;

  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <p className="text-[13px] font-medium text-ink">
          {meta.label}
          <span className="ml-2 text-[11px] font-normal text-ink-3">
            {directionLabel(metricKey)}
          </span>
        </p>
        <div className="flex items-center gap-2">
          <span className="tabular text-[12px] text-ink-3">
            {formatMetric(metricKey, beforeValue)}
          </span>
          {afterValue !== undefined ? (
            <>
              <span aria-hidden className="text-[11px] text-ink-4">
                &rarr;
              </span>
              <span className="tabular text-[13px] font-semibold text-ink">
                {formatMetric(metricKey, afterValue)}
              </span>
              {polarity ? (
                <Pill
                  tone={
                    polarity === "improvement"
                      ? "positive"
                      : polarity === "regression"
                        ? "negative"
                        : "neutral"
                  }
                >
                  {formatDelta(metricKey, delta!)}{" "}
                  {polarity === "unchanged" ? "unchanged" : polarity}
                </Pill>
              ) : null}
            </>
          ) : null}
        </div>
      </div>

      <div className="mt-1.5 space-y-1">
        <Bar fraction={metricFraction(metricKey, beforeValue)} tone="before" />
        {afterValue !== undefined ? (
          <Bar fraction={metricFraction(metricKey, afterValue)} tone="after" />
        ) : null}
      </div>

      <div className="mt-1 flex justify-between text-[10px] text-ink-4">
        <span className="tabular">{min}</span>
        <span className="tabular">{max}</span>
      </div>
    </div>
  );
}

function Bar({ fraction, tone }: { fraction: number; tone: "before" | "after" }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-surface-3">
      <div
        className={cx(
          "h-full rounded-full transition-[width] duration-700 [transition-timing-function:var(--ease)]",
          tone === "before" ? "bg-ink-4" : "bg-accent",
        )}
        style={{ width: `${Math.max(fraction * 100, fraction > 0 ? 1.5 : 0)}%` }}
      />
    </div>
  );
}
