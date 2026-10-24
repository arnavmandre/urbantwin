"use client";

import { Card, CardHeader } from "@/components/ui/Card";
import { Dot } from "@/components/ui/Pill";
import { BEHAVIORS, BEHAVIOR_META } from "@/lib/behaviors";
import { cx } from "@/lib/cx";
import { formatCount, formatPercent } from "@/lib/metric-format";
import type { BehaviorCounts, CitizenBehavior } from "@/lib/types";

/**
 * Behaviour distribution and the fixed six-colour legend.
 *
 * The colours are the ones `phase9/agents_instancer.py` writes into the USD
 * stage, so an agent that is yellow in the viewport is yellow here.
 */
export function BehaviorLegend({
  before,
  after,
}: {
  before: BehaviorCounts;
  after?: BehaviorCounts;
}) {
  const beforeTotal = total(before);
  const afterTotal = after ? total(after) : 0;

  return (
    <Card>
      <CardHeader
        eyebrow="Simulated behaviour"
        title="What the citizens did"
        description="Each citizen resolves to exactly one behaviour. Behaviours not triggered by this scenario stay at zero."
      />

      <div className="mt-5 space-y-4">
        <StackedBar label="Before" counts={before} total={beforeTotal} />
        {after ? <StackedBar label="After" counts={after} total={afterTotal} /> : null}
      </div>

      <ul className="mt-5 grid gap-x-6 gap-y-2.5 sm:grid-cols-2">
        {BEHAVIORS.map((behavior) => {
          const meta = BEHAVIOR_META[behavior];
          const beforeCount = before[behavior] ?? 0;
          const afterCount = after?.[behavior];
          return (
            <li key={behavior} className="flex items-start gap-2.5">
              <Dot color={meta.hex} className="mt-1.5" />
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-2">
                  <p className="text-[13px] font-medium text-ink">
                    {meta.label}
                    <span className="ml-1.5 text-[11px] font-normal text-ink-4">
                      {meta.colorName}
                    </span>
                  </p>
                  <p className="tabular shrink-0 text-[12px] text-ink-2">
                    {formatCount(beforeCount)}
                    {afterCount !== undefined ? (
                      <>
                        <span aria-hidden className="mx-1 text-ink-4">
                          &rarr;
                        </span>
                        <span className="font-semibold text-ink">
                          {formatCount(afterCount)}
                        </span>
                      </>
                    ) : null}
                  </p>
                </div>
                <p className="text-[11px] leading-relaxed text-ink-3">{meta.meaning}</p>
              </div>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function StackedBar({
  label,
  counts,
  total: sum,
}: {
  label: string;
  counts: BehaviorCounts;
  total: number;
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <p className="text-[12px] font-medium text-ink-2">{label}</p>
        <p className="tabular text-[11px] text-ink-3">
          {formatCount(sum)} citizens simulated
        </p>
      </div>
      {/* 2px surface gaps separate segments instead of strokes around them. */}
      <div className="mt-1.5 flex h-3 w-full gap-[2px] overflow-hidden rounded-full">
        {BEHAVIORS.map((behavior) => {
          const count = counts[behavior] ?? 0;
          if (count === 0) return null;
          return (
            <div
              key={behavior}
              title={`${BEHAVIOR_META[behavior].label}: ${formatCount(count)} (${formatPercent(count, sum)})`}
              className={cx("h-full transition-[width] duration-700 [transition-timing-function:var(--ease)]")}
              style={{ width: `${(count / sum) * 100}%`, background: BEHAVIOR_META[behavior].hex }}
            />
          );
        })}
      </div>
      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1">
        {BEHAVIORS.filter((b) => (counts[b] ?? 0) > 0).map((behavior) => (
          <span key={behavior} className="flex items-center gap-1.5 text-[11px] text-ink-3">
            <Dot color={BEHAVIOR_META[behavior].hex} />
            {BEHAVIOR_META[behavior].label} {formatPercent(counts[behavior] ?? 0, sum)}
          </span>
        ))}
      </div>
    </div>
  );
}

function total(counts: BehaviorCounts): number {
  return (Object.keys(counts) as CitizenBehavior[]).reduce(
    (sum, key) => sum + (counts[key] ?? 0),
    0,
  );
}
