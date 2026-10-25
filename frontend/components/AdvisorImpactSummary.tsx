"use client";

import { Card, CardHeader } from "@/components/ui/Card";
import { DeltaPill } from "@/components/ui/DeltaPill";
import { Pill } from "@/components/ui/Pill";
import { METRIC_META, deltaPolarity, formatMetric } from "@/lib/metric-format";
import type { InterventionParameters, MetricKey, SimulationMetrics } from "@/lib/types";

const ACTION_LABEL: Record<string, string> = {
  shade_boost: "shade",
  drainage_boost: "drainage",
  route_capacity_boost: "pedestrian routes",
};

const TONE = { improvement: "positive", regression: "negative", unchanged: "neutral" } as const;
const VERDICT = { improvement: "Improved", regression: "Worsened", unchanged: "No change" } as const;

const SUPPORTING_METRICS: MetricKey[] = [
  "comfort",
  "mobility",
  "safety",
  "heat_stress",
  "rain_impact",
  "crowding",
];

export function AdvisorImpactSummary({
  before,
  after,
  intervention,
}: {
  before: SimulationMetrics;
  after: SimulationMetrics;
  intervention: InterventionParameters;
}) {
  const actions = Object.keys(intervention)
    .filter((key) => typeof intervention[key as keyof InterventionParameters] === "number")
    .map((key) => ACTION_LABEL[key] ?? key);
  const indexDelta = after.human_experience_index - before.human_experience_index;
  const polarity = deltaPolarity("human_experience_index", indexDelta);

  if (actions.length === 0) {
    return null;
  }

  return (
    <Card className="border-accent-line bg-accent-soft">
      <CardHeader
        eyebrow="Measured intervention result"
        title="What the intervention changed"
        description={`The simulator re-ran the same citizens with ${actions.join(" and ")} implemented. These are calculated results, not claims from the AI advisor.`}
        actions={
          <Pill tone={TONE[polarity]}>
            {VERDICT[polarity]}
          </Pill>
        }
      />

      <div className="mt-5 rounded-[14px] border border-accent-line bg-surface p-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-3">
          Human Experience Index
        </p>
        <div className="mt-1 flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <span className="tabular text-2xl font-semibold text-ink">
            {formatMetric("human_experience_index", before.human_experience_index)}
          </span>
          <span className="text-ink-4">→</span>
          <span className="tabular text-2xl font-semibold text-ink">
            {formatMetric("human_experience_index", after.human_experience_index)}
          </span>
          <DeltaPill metricKey="human_experience_index" delta={indexDelta} />
        </div>
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {SUPPORTING_METRICS.map((metric) => {
          const delta = after[metric] - before[metric];
          return (
            <div key={metric} className="rounded-[12px] border border-hairline bg-surface px-3 py-2.5">
              <div className="flex items-start justify-between gap-2">
                <p className="text-[11px] text-ink-3">{METRIC_META[metric].label}</p>
                <DeltaPill compact metricKey={metric} delta={delta} />
              </div>
              <p className="mt-1 tabular text-[13px] font-semibold text-ink">
                {formatMetric(metric, before[metric])} → {formatMetric(metric, after[metric])}
              </p>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
