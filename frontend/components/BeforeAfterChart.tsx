"use client";

import { Card, CardHeader } from "@/components/ui/Card";
import { DeltaPill } from "@/components/ui/DeltaPill";
import { cx } from "@/lib/cx";
import {
  COMPARISON_METRICS,
  METRIC_META,
  deltaPolarity,
  formatMetric,
  metricFraction,
} from "@/lib/metric-format";
import type { MetricKey, SimulationMetrics } from "@/lib/types";

const SCORE_TICKS = [0, 25, 50, 75, 100];
const TRAVEL_TICKS = [0, 2.5, 5, 7.5, 10];

/**
 * Before/after as a dumbbell chart: one row per metric, the baseline as a ring
 * and the intervention as a filled dot on a shared axis, joined by the change.
 *
 * Rows are sorted by how far the metric moved, so the intervention's main
 * effect is the first thing read. Whether a move is good is stated per row
 * (DeltaPill) because the direction differs by metric. Travel time has its own
 * 0-10 minute axis and is drawn separately, never on the 0-100 score axis.
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
  const rows = [...COMPARISON_METRICS].sort((a, b) =>
    after ? Math.abs(after[b] - before[b]) - Math.abs(after[a] - before[a]) : 0,
  );
  const improved = after
    ? rows.filter((k) => deltaPolarity(k, after[k] - before[k]) === "improvement").length
    : 0;
  const worsened = after
    ? rows.filter((k) => deltaPolarity(k, after[k] - before[k]) === "regression").length
    : 0;

  return (
    <Card>
      <CardHeader
        eyebrow="Comparison"
        title="Before and after"
        description={
          after
            ? `${improved} of ${rows.length} scores improved${worsened ? `, ${worsened} worsened` : ""}. Largest change first. ${interventionLabel ?? ""}`.trim()
            : "No intervention arm was produced for this run, so only the current state is shown."
        }
        actions={<Legend hasAfter={Boolean(after)} />}
      />

      <div className="mt-5" role="list" aria-label="Scores before and after the intervention, 0 to 100">
        {rows.map((key) => (
          <DumbbellRow key={key} metricKey={key} beforeValue={before[key]} afterValue={after?.[key]} />
        ))}
        <AxisRow ticks={SCORE_TICKS} />
      </div>

      <div className="mt-5 border-t border-hairline pt-4" role="list" aria-label="Mean travel time in minutes">
        <DumbbellRow
          metricKey="mean_travel_minutes"
          beforeValue={before.mean_travel_minutes}
          afterValue={after?.mean_travel_minutes}
        />
        <AxisRow ticks={TRAVEL_TICKS} unit=" min" />
      </div>

      <details className="mt-4 rounded-[12px] border border-hairline px-3 py-2">
        <summary className="cursor-pointer text-[12px] font-semibold text-ink-2">Show as table</summary>
        <table className="tabular mt-2 w-full text-[12px]">
          <thead>
            <tr className="text-left text-ink-3">
              <th className="py-1 font-medium">Metric</th>
              <th className="py-1 text-right font-medium">Before</th>
              {after ? <th className="py-1 text-right font-medium">After</th> : null}
              {after ? <th className="py-1 text-right font-medium">Change</th> : null}
            </tr>
          </thead>
          <tbody>
            {[...rows, "mean_travel_minutes" as MetricKey].map((key) => (
              <tr key={key} className="border-t border-hairline text-ink-2">
                <td className="py-1">{METRIC_META[key].label}</td>
                <td className="py-1 text-right">{formatMetric(key, before[key])}</td>
                {after ? <td className="py-1 text-right text-ink">{formatMetric(key, after[key])}</td> : null}
                {after ? (
                  <td className="py-1 text-right">
                    <DeltaPill metricKey={key} delta={after[key] - before[key]} />
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </Card>
  );
}

function Legend({ hasAfter }: { hasAfter: boolean }) {
  return (
    <div className="flex items-center gap-3 text-[11px] text-ink-3">
      <span className="flex items-center gap-1.5">
        <BeforeMark /> Before
      </span>
      {hasAfter ? (
        <span className="flex items-center gap-1.5">
          <AfterMark /> After
        </span>
      ) : null}
    </div>
  );
}

/** Label | plot | change. The plot column is the only one that stretches. */
const ROW_GRID = "grid grid-cols-[minmax(0,9.5rem)_minmax(0,1fr)_6.75rem] items-center gap-x-3";

function DumbbellRow({
  metricKey,
  beforeValue,
  afterValue,
}: {
  metricKey: MetricKey;
  beforeValue: number;
  afterValue?: number;
}) {
  const meta = METRIC_META[metricKey];
  const b = metricFraction(metricKey, beforeValue) * 100;
  const a = afterValue === undefined ? null : metricFraction(metricKey, afterValue) * 100;
  const lo = a === null ? b : Math.min(a, b);
  const hi = a === null ? b : Math.max(a, b);
  const values =
    `${meta.label}: before ${formatMetric(metricKey, beforeValue)}` +
    (afterValue === undefined ? "" : `, after ${formatMetric(metricKey, afterValue)}`) +
    (metricKey === "mean_travel_minutes" ? " minutes" : " out of 100");

  return (
    <div role="listitem" aria-label={values} className={cx(ROW_GRID, "group relative py-1.5")}>
      <div className="min-w-0">
        <p className="truncate text-[12.5px] font-medium text-ink">{meta.label}</p>
        <p className="text-[10.5px] text-ink-3">
          {meta.direction === "higher_is_better" ? "↑ higher is better" : "↓ lower is better"}
        </p>
      </div>

      {/* Plot. Hairline gridlines at the tick positions; the dots carry a 2px
          surface ring so they stay legible where they overlap. */}
      <div className="relative h-6">
        <div aria-hidden className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-hairline" />
        {[0, 25, 50, 75, 100].map((pct) => (
          <span key={pct} aria-hidden className="absolute inset-y-0 w-px bg-hairline" style={{ left: `${pct}%` }} />
        ))}
        {a !== null ? (
          <div
            aria-hidden
            className="absolute top-1/2 h-[3px] -translate-y-1/2 rounded-full bg-ink-4/45 transition-[left,width] duration-700 [transition-timing-function:var(--ease)]"
            style={{ left: `${lo}%`, width: `${hi - lo}%` }}
          />
        ) : null}
        <Dot left={b}>
          <BeforeMark />
        </Dot>
        {a !== null ? (
          <Dot left={a}>
            <AfterMark />
          </Dot>
        ) : null}

        {/* Hover detail: exact values. The row is the hit target, so it is far
            larger than the 10px marks. */}
        <div
          aria-hidden
          className="pointer-events-none absolute bottom-full z-10 mb-1 -translate-x-1/2 whitespace-nowrap rounded-[8px] border border-hairline bg-surface px-2 py-1 text-[11px] text-ink-2 opacity-0 shadow-[var(--shadow-card)] transition-opacity group-hover:opacity-100"
          style={{ left: `${(lo + hi) / 2}%` }}
        >
          <span className="tabular">
            {formatMetric(metricKey, beforeValue)}
            {afterValue !== undefined ? (
              <>
                {" → "}
                <span className="font-semibold text-ink">{formatMetric(metricKey, afterValue)}</span>
              </>
            ) : null}
            {metricKey === "mean_travel_minutes" ? " min" : ""}
          </span>
        </div>
      </div>

      <div className="flex justify-end">
        {afterValue !== undefined ? (
          <DeltaPill metricKey={metricKey} delta={afterValue - beforeValue} />
        ) : (
          <span className="tabular text-[12px] text-ink-2">{formatMetric(metricKey, beforeValue)}</span>
        )}
      </div>
    </div>
  );
}

function Dot({ left, children }: { left: number; children: React.ReactNode }) {
  return (
    <span
      aria-hidden
      className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 transition-[left] duration-700 [transition-timing-function:var(--ease)]"
      style={{ left: `${left}%` }}
    >
      {children}
    </span>
  );
}

function BeforeMark() {
  // Border colour set inline: the border-width utility resets the colour
  // utility in this Tailwind build, which left the ring pale grey.
  return (
    <span
      className="block size-[12px] rounded-full border-[2.5px] border-solid bg-surface ring-2 ring-surface"
      style={{ borderColor: "var(--series-before)" }}
    />
  );
}

function AfterMark() {
  return <span className="block size-[11px] rounded-full bg-series-after ring-2 ring-surface" />;
}

function AxisRow({ ticks, unit = "" }: { ticks: number[]; unit?: string }) {
  const max = ticks[ticks.length - 1];
  return (
    <div aria-hidden className={cx(ROW_GRID, "pt-0.5")}>
      <span />
      <div className="relative h-4">
        {ticks.map((tick) => (
          <span
            key={tick}
            className="tabular absolute -translate-x-1/2 text-[10px] text-ink-4"
            style={{ left: `${(tick / max) * 100}%` }}
          >
            {tick}
            {tick === max ? unit : ""}
          </span>
        ))}
      </div>
      <span />
    </div>
  );
}
