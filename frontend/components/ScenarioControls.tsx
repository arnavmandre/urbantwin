"use client";

import { useId } from "react";

import { Card, CardHeader } from "@/components/ui/Card";
import { cx } from "@/lib/cx";
import {
  SCENARIO_FIELD_META,
  formatScenarioValue,
} from "@/lib/metric-format";
import type {
  CityKey,
  ScenarioCatalog,
  ScenarioField,
  ScenarioInput,
} from "@/lib/types";

export const CITY_LABEL: Record<CityKey, string> = {
  pune: "Pune",
};

const RANGES_NOTE =
  "Ranges are the simulator's accepted inputs. Values outside them are refused before a run starts.";

/**
 * One-line helpers shown under each slider. The full explanations in
 * SCENARIO_FIELD_META stay available, unabridged, under "Input details".
 */
const SHORT_HELP: Record<ScenarioField, string> = {
  temperature: "Ambient air temperature for the whole run.",
  humidity: "Raises the effective heat load.",
  rainfall: "Prototype scale; drives the rain and flood-risk proxy.",
  population: "Demand scale, not a headcount and not the rendered agents.",
};

const FIELD_ORDER: ScenarioField[] = [
  "temperature",
  "humidity",
  "rainfall",
  "population",
];

export function ScenarioControls({
  catalog,
  scenario,
  onScenarioChange,
  applyInterventions,
  onApplyInterventionsChange,
  onRun,
  onCancel,
  busy,
  fieldErrors,
  formError,
  className,
  plain = false,
  city,
  streamCity,
}: {
  city: CityKey;
  /** City the Kit stream was launched on, or null when no stream is available. */
  streamCity: CityKey | null;
  catalog: ScenarioCatalog;
  scenario: ScenarioInput;
  onScenarioChange: (scenario: ScenarioInput) => void;
  applyInterventions: boolean;
  onApplyInterventionsChange: (value: boolean) => void;
  onRun: () => void;
  onCancel: () => void;
  busy: boolean;
  fieldErrors: Partial<Record<ScenarioField, string>>;
  formError: string | null;
  className?: string;
  /** Render without card chrome, for a container that already frames it. */
  plain?: boolean;
}) {
  const activePreset = catalog.presets.find((preset) =>
    FIELD_ORDER.every((field) => preset[field] === scenario[field]),
  );

  return (
    <Frame plain={plain} className={className}>
      {plain ? (
        // The surrounding drawer already titles this "Simulation controls".
        <p className="text-[12.5px] leading-relaxed text-ink-2">{RANGES_NOTE}</p>
      ) : (
        <CardHeader eyebrow="Scenario" title="Simulation controls" description={RANGES_NOTE} />
      )}

      <div className="mt-3 flex items-center justify-between gap-3">
        <span className="text-[13px] font-medium text-ink">City</span>
        <span className="text-[13px] text-ink-2">Pune</span>
      </div>
      {streamCity && streamCity !== city ? (
        <p className="mt-1.5 text-[11px] leading-relaxed text-ink-3">
          The Omniverse stream is showing {CITY_LABEL[streamCity]}. Results will be for{" "}
          {CITY_LABEL[city]}; relaunch with{" "}
          <code className="font-mono">demo_launch.ps1 -City {city}</code> to see it streamed.
        </p>
      ) : null}

      <div className="mt-3 flex flex-wrap gap-2">
        {catalog.presets.map((preset) => {
          const active = activePreset?.id === preset.id;
          return (
            <button
              key={preset.id}
              type="button"
              disabled={busy}
              title={preset.description}
              onClick={() =>
                onScenarioChange({
                  temperature: preset.temperature,
                  humidity: preset.humidity,
                  rainfall: preset.rainfall,
                  population: preset.population,
                })
              }
              className={cx(
                "rounded-full border px-3 py-1.5 text-[12px] font-medium transition-all duration-200 [transition-timing-function:var(--ease)]",
                active
                  ? "border-accent-line bg-accent-soft text-accent"
                  : "border-hairline text-ink-2 hover:text-ink",
                busy && "cursor-not-allowed opacity-50",
              )}
            >
              {preset.label ?? preset.id}
            </button>
          );
        })}
      </div>

      {/* One column at every width: the controls live in a fixed-width drawer. */}
      <div className="mt-4 space-y-4">
        {FIELD_ORDER.map((field) => (
          <ScenarioSlider
            key={field}
            field={field}
            value={scenario[field]}
            range={catalog.constraints[field]}
            disabled={busy}
            error={fieldErrors[field]}
            onChange={(value) => onScenarioChange({ ...scenario, [field]: value })}
          />
        ))}
      </div>

      <label
        className={cx(
          "mt-4 flex cursor-pointer items-start gap-3 rounded-[12px] border border-hairline bg-surface-2 p-2.5",
          busy && "cursor-not-allowed opacity-60",
        )}
      >
        <input
          type="checkbox"
          checked={applyInterventions}
          disabled={busy}
          onChange={(event) => onApplyInterventionsChange(event.target.checked)}
          className="mt-0.5 size-4 accent-[var(--accent)]"
        />
        <span>
          <span className="block text-[13px] font-medium text-ink">
            Apply the advisor&rsquo;s recommended interventions and re-simulate
          </span>
          <span className="mt-0.5 block text-[12px] leading-relaxed text-ink-3">
            Produces the &ldquo;after&rdquo; arm. Only interventions the simulator
            actually implements are applied.
          </span>
        </span>
      </label>

      {formError ? (
        <p
          role="alert"
          className="mt-3 rounded-[12px] border border-[color:var(--negative)]/30 bg-negative-soft px-3 py-2 text-[12px] leading-relaxed text-negative"
        >
          {formError}
        </p>
      ) : null}

      {/* In the drawer the Run row stays pinned to the bottom of the scroll
          area, so it is reachable on short screens without scrolling. The
          negative offsets cancel the drawer body's padding. */}
      <div
        className={cx(
          "mt-4 flex items-center gap-2",
          plain &&
            "sticky -bottom-4 z-10 -mx-4 border-t border-hairline bg-surface px-4 py-3 sm:-bottom-5 sm:-mx-5 sm:px-5",
        )}
      >
        <button
          type="button"
          onClick={onRun}
          disabled={busy}
          className={cx(
            "flex-1 rounded-[12px] px-4 py-2.5 text-[14px] font-semibold transition-all duration-200 [transition-timing-function:var(--ease)]",
            busy
              ? "cursor-not-allowed bg-surface-3 text-ink-3"
              : "bg-accent text-accent-ink shadow-[var(--shadow-card)] hover:bg-accent-hover active:scale-[0.99]",
          )}
        >
          {busy ? "Simulation in progress\u2026" : "Run simulation"}
        </button>
        {busy ? (
          <button
            type="button"
            onClick={onCancel}
            className="rounded-[12px] border border-hairline px-4 py-2.5 text-[13px] font-semibold text-ink-2 transition-colors hover:text-ink"
          >
            Cancel
          </button>
        ) : null}
      </div>

      {busy ? (
        <p className="mt-2 text-[12px] leading-relaxed text-ink-3">
          One simulation at a time: Run is disabled while a run is active.
        </p>
      ) : null}

      <details className="mt-3 rounded-[12px] border border-hairline px-3 py-2">
        <summary className="cursor-pointer text-[12px] font-semibold text-ink-2">
          Input details
        </summary>
        <dl className="mt-2 space-y-2">
          {FIELD_ORDER.map((field) => (
            <div key={field}>
              <dt className="text-[12px] font-medium text-ink">
                {SCENARIO_FIELD_META[field].label}{" "}
                <span className="font-normal text-ink-3">
                  {formatScenarioValue(field, catalog.constraints[field][0])} to{" "}
                  {formatScenarioValue(field, catalog.constraints[field][1])},{" "}
                  {catalog.units[field]}
                </span>
              </dt>
              <dd className="text-[11.5px] leading-relaxed text-ink-2">
                {SCENARIO_FIELD_META[field].help}
              </dd>
            </div>
          ))}
        </dl>
      </details>
    </Frame>
  );
}

function Frame({
  plain,
  className,
  children,
}: {
  plain: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  return plain ? <div className={className}>{children}</div> : <Card className={className}>{children}</Card>;
}

function ScenarioSlider({
  field,
  value,
  range,
  disabled,
  error,
  onChange,
}: {
  field: ScenarioField;
  value: number;
  range: [number, number];
  disabled: boolean;
  error?: string;
  onChange: (value: number) => void;
}) {
  const id = useId();
  const meta = SCENARIO_FIELD_META[field];
  const [min, max] = range;
  const outOfRange = value < min || value > max;
  const fill = (Math.min(max, Math.max(min, value)) - min) / (max - min) * 100;

  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <label htmlFor={id} className="text-[13px] font-medium text-ink">
          {meta.label}
        </label>
        <span className="flex items-baseline gap-1">
          {/* Typed values are intentionally not clamped: the backend is the
              authority on what it will accept, and its rejection is what the
              form shows. The slider covers the valid range. */}
          <input
            type="number"
            aria-label={`${meta.label} value`}
            value={Number.isFinite(value) ? value : ""}
            step={meta.step}
            disabled={disabled}
            onChange={(event) => {
              const next = Number(event.target.value);
              if (event.target.value !== "" && Number.isFinite(next)) onChange(next);
            }}
            className={cx(
              "tabular no-spinner w-[8ch] rounded-[8px] border bg-transparent px-1.5 py-0.5 text-right text-[14px] font-semibold tracking-[-0.01em] text-ink",
              outOfRange || error
                ? "border-[color:var(--negative)] text-negative"
                : "border-transparent hover:border-hairline focus:border-hairline",
            )}
          />
          <span className="text-[11px] font-medium text-ink-3">
            {field === "population" ? "equivalent" : meta.unit}
          </span>
        </span>
      </div>

      <input
        id={id}
        type="range"
        className="slider mt-1"
        style={{ ["--fill" as string]: `${fill}%` }}
        min={min}
        max={max}
        step={meta.step}
        value={value}
        disabled={disabled}
        aria-describedby={`${id}-help`}
        onChange={(event) => onChange(Number(event.target.value))}
      />

      <div className="flex items-center justify-between">
        <span className="tabular text-[11px] text-ink-3">
          {formatScenarioValue(field, min)}
        </span>
        <span className="tabular text-[11px] text-ink-3">
          {formatScenarioValue(field, max)}
        </span>
      </div>

      <p id={`${id}-help`} className="text-[11px] leading-relaxed text-ink-3">
        {SHORT_HELP[field]}
      </p>

      {error || outOfRange ? (
        <p role="alert" className="mt-1 text-[11px] font-medium text-negative">
          {error ?? `Outside the simulator's accepted range of ${min} to ${max}.`}
        </p>
      ) : null}
    </div>
  );
}
