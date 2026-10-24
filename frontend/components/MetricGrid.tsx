"use client";

import { DeltaPill } from "@/components/ui/DeltaPill";
import { cx } from "@/lib/cx";
import {
  HEADLINE_METRICS,
  METRIC_META,
  directionLabel,
  formatMetric,
  metricFraction,
} from "@/lib/metric-format";
import type { MetricKey, RunState, SimulationMetrics } from "@/lib/types";

/**
 * Headline metric tiles.
 *
 * A tile always states its direction, because the sign of a change means
 * nothing on its own: +22.8 safety is an improvement, +22.8 heat stress is not.
 */
export function MetricGrid({
  metrics,
  comparison,
  state,
  keys = HEADLINE_METRICS,
  className,
}: {
  metrics: SimulationMetrics;
  /** The other arm, when a before/after pair exists. */
  comparison?: SimulationMetrics;
  state: RunState;
  keys?: MetricKey[];
  className?: string;
}) {
  return (
    <div className={cx("grid gap-3 sm:grid-cols-2", className)}>
      {keys.map((key) => (
        <MetricTile
          key={key}
          metricKey={key}
          value={metrics[key]}
          compareValue={comparison?.[key]}
          state={state}
        />
      ))}
    </div>
  );
}

function MetricTile({
  metricKey,
  value,
  compareValue,
  state,
}: {
  metricKey: MetricKey;
  value: number;
  compareValue?: number;
  state: RunState;
}) {
  const meta = METRIC_META[metricKey];
  // "after" is always measured against "before", whichever arm is on screen.
  const delta =
    compareValue === undefined
      ? null
      : state === "after"
        ? value - compareValue
        : compareValue - value;
  const otherState = state === "after" ? "before" : "after";

  return (
    <div className="rounded-[14px] border border-hairline bg-surface-2 p-4">
      <div className="flex items-start justify-between gap-2">
        <p className="text-[12px] font-medium text-ink-2">{meta.label}</p>
        {delta !== null ? (
          <DeltaPill
            compact
            metricKey={metricKey}
            delta={delta}
            title={
              state === "after"
                ? "Change from before to after the intervention"
                : "Change the intervention would make"
            }
          />
        ) : null}
      </div>

      <p className="tabular mt-2 text-[30px] font-semibold leading-none tracking-[-0.03em] text-ink">
        {formatMetric(metricKey, value)}
        <span className="ml-1 text-[13px] font-medium text-ink-3">{meta.unit}</span>
      </p>

      {/* Meter in the colour of the arm on screen. A tick marks the other arm,
          so the tile shows where the value came from (or would go). */}
      <div className="relative mt-3 h-1.5 w-full rounded-full bg-surface-3">
        <div
          className={cx(
            "h-full rounded-full transition-[width] duration-500 [transition-timing-function:var(--ease)]",
            state === "after" ? "bg-series-after" : "bg-series-before",
          )}
          style={{ width: `${metricFraction(metricKey, value) * 100}%` }}
        />
        {compareValue !== undefined ? (
          <span
            title={`${otherState === "before" ? "Before" : "After"}: ${formatMetric(metricKey, compareValue)}`}
            className="absolute -top-1 h-3.5 w-[3px] -translate-x-1/2 rounded-full bg-ink-2 ring-2 ring-surface-2"
            style={{ left: `${metricFraction(metricKey, compareValue) * 100}%` }}
          />
        ) : null}
      </div>

      <p className="mt-2 text-[11px] text-ink-3">
        {directionLabel(metricKey)}
        {compareValue !== undefined ? (
          <span className="tabular">
            {" · "}
            {otherState === "before" ? "was" : "after"} {formatMetric(metricKey, compareValue)}
          </span>
        ) : null}
      </p>
    </div>
  );
}
