/**
 * Metric direction, formatting and delta polarity.
 *
 * Direction matters more than the number: a 22.78 rise in safety is good, a
 * 22.78 rise in heat stress is bad. Everything that renders a metric goes
 * through here so that "higher is worse" / "higher is better" can never be
 * decided ad hoc in a component.
 */
import type { MetricKey, ScenarioField, SimulationMetrics } from "./types";

export type MetricDirection = "higher_is_better" | "higher_is_worse";

export interface MetricMeta {
  key: MetricKey;
  label: string;
  short: string;
  direction: MetricDirection;
  unit: string;
  /** Axis range for before/after comparison. Both arms share it. */
  range: [number, number];
  help: string;
}

export const METRIC_META: Record<MetricKey, MetricMeta> = {
  human_experience_index: {
    key: "human_experience_index",
    label: "Human Experience Index",
    short: "HEI",
    direction: "higher_is_better",
    unit: "/100",
    range: [0, 100],
    help: "Composite prototype score across comfort, safety and mobility.",
  },
  citizen_comfort: {
    key: "citizen_comfort",
    label: "Citizen comfort",
    short: "Citizen comfort",
    direction: "higher_is_better",
    unit: "/100",
    range: [0, 100],
    help: "Population-weighted comfort across the simulated citizens.",
  },
  comfort: {
    key: "comfort",
    label: "City comfort",
    short: "City comfort",
    direction: "higher_is_better",
    unit: "/100",
    range: [0, 100],
    help: "City-level comfort, unweighted by who is actually out walking.",
  },
  safety: {
    key: "safety",
    label: "Safety",
    short: "Safety",
    direction: "higher_is_better",
    unit: "/100",
    range: [0, 100],
    help: "Heuristic pedestrian safety under the scenario's weather.",
  },
  mobility: {
    key: "mobility",
    label: "Mobility",
    short: "Mobility",
    direction: "higher_is_better",
    unit: "/100",
    range: [0, 100],
    help: "How freely pedestrians can move given surface and crowding penalties.",
  },
  heat_stress: {
    key: "heat_stress",
    label: "Heat stress",
    short: "Heat",
    direction: "higher_is_worse",
    unit: "/100",
    range: [0, 100],
    help: "Heat load on pedestrians. A prototype proxy, not UTCI or WBGT.",
  },
  cold_stress: {
    key: "cold_stress",
    label: "Cold stress",
    short: "Cold",
    direction: "higher_is_worse",
    unit: "/100",
    range: [0, 100],
    help: "Cold load on pedestrians. Zero in warm scenarios.",
  },
  rain_impact: {
    key: "rain_impact",
    label: "Rain impact",
    short: "Rain",
    direction: "higher_is_worse",
    unit: "/100",
    range: [0, 100],
    help: "Rainfall and flood-risk proxy. Not a hydraulic flood model.",
  },
  crowding: {
    key: "crowding",
    label: "Crowding",
    short: "Crowding",
    direction: "higher_is_worse",
    unit: "/100",
    range: [0, 100],
    help: "Corridor and destination crowding from iterative route assignment.",
  },
  mean_travel_minutes: {
    key: "mean_travel_minutes",
    label: "Mean travel time",
    short: "Travel",
    direction: "higher_is_worse",
    unit: " min",
    range: [0, 10],
    help: "Average simulated walking time across all citizens.",
  },
};

/** Order used by the headline tiles: the four a judge should read first. */
export const HEADLINE_METRICS: MetricKey[] = [
  "human_experience_index",
  "citizen_comfort",
  "safety",
  "mobility",
];

/** Order used by the full comparison chart. */
export const COMPARISON_METRICS: MetricKey[] = [
  "human_experience_index",
  "citizen_comfort",
  "comfort",
  "safety",
  "mobility",
  "heat_stress",
  "cold_stress",
  "rain_impact",
  "crowding",
];

export function metricValue(metrics: SimulationMetrics, key: MetricKey): number {
  return metrics[key];
}

export function formatMetric(key: MetricKey, value: number): string {
  const decimals = key === "mean_travel_minutes" ? 2 : 1;
  return value.toFixed(decimals);
}

export function formatMetricWithUnit(key: MetricKey, value: number): string {
  return `${formatMetric(key, value)}${METRIC_META[key].unit}`;
}

export type DeltaPolarity = "improvement" | "regression" | "unchanged";

/** A change is an improvement only relative to the metric's own direction. */
export function deltaPolarity(key: MetricKey, delta: number): DeltaPolarity {
  const epsilon = key === "mean_travel_minutes" ? 0.005 : 0.05;
  if (Math.abs(delta) < epsilon) return "unchanged";
  const better = METRIC_META[key].direction === "higher_is_better" ? delta > 0 : delta < 0;
  return better ? "improvement" : "regression";
}

export function formatDelta(key: MetricKey, delta: number): string {
  const decimals = key === "mean_travel_minutes" ? 2 : 1;
  const magnitude = Math.abs(delta).toFixed(decimals);
  // A change that rounds to zero is shown as \u00b10.0, never \u22120.0.
  const sign = Number(magnitude) === 0 ? "\u00b1" : delta > 0 ? "+" : "\u2212";
  return `${sign}${magnitude}`;
}

export function directionLabel(key: MetricKey): string {
  return METRIC_META[key].direction === "higher_is_better"
    ? "Higher is better"
    : "Higher is worse";
}

/** Fraction of the shared axis a value occupies, for bars and charts. */
export function metricFraction(key: MetricKey, value: number): number {
  const [min, max] = METRIC_META[key].range;
  return Math.min(1, Math.max(0, (value - min) / (max - min)));
}

// --------------------------------------------------------------------------
// Scenario fields
// --------------------------------------------------------------------------

export interface ScenarioFieldMeta {
  key: ScenarioField;
  label: string;
  unit: string;
  step: number;
  help: string;
}

export const SCENARIO_FIELD_META: Record<ScenarioField, ScenarioFieldMeta> = {
  temperature: {
    key: "temperature",
    label: "Temperature",
    unit: "\u00b0C",
    step: 1,
    help: "Ambient air temperature for the whole run.",
  },
  humidity: {
    key: "humidity",
    label: "Humidity",
    unit: "%",
    step: 1,
    help: "Relative humidity. Raises the effective heat load.",
  },
  rainfall: {
    key: "rainfall",
    label: "Rainfall",
    unit: "mm",
    step: 1,
    help: "Prototype rainfall scale driving the rain and flood-risk proxy.",
  },
  population: {
    key: "population",
    label: "Population equivalent",
    unit: "",
    step: 1000,
    help:
      "Demand scale for the area, not a headcount and not the number of people " +
      "drawn. 1,000 survey-calibrated citizens are simulated and at most 500 " +
      "representative agents are rendered.",
  },
};

const NUMBER = new Intl.NumberFormat("en-GB");

export function formatScenarioValue(field: ScenarioField, value: number): string {
  const meta = SCENARIO_FIELD_META[field];
  if (field === "population") return NUMBER.format(value);
  return `${value}${meta.unit}`;
}

export function formatCount(value: number): string {
  return NUMBER.format(value);
}

export function formatPercent(value: number, total: number): string {
  if (total <= 0) return "0%";
  const pct = (value / total) * 100;
  return `${pct >= 10 || pct === 0 ? pct.toFixed(0) : pct.toFixed(1)}%`;
}
