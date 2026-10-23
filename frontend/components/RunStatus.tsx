"use client";

import { Card, CardHeader } from "@/components/ui/Card";
import { Dot, Pill, type PillTone } from "@/components/ui/Pill";
import { cx } from "@/lib/cx";
import { formatScenarioValue } from "@/lib/metric-format";
import type { RunStatus as RunStatusValue, RunSummary } from "@/lib/types";

const STATUS_STYLE: Record<
  RunStatusValue | "idle",
  { tone: PillTone; label: string; color: string }
> = {
  idle: { tone: "neutral", label: "Idle", color: "var(--ink-4)" },
  queued: { tone: "caution", label: "Queued", color: "var(--caution)" },
  running: { tone: "caution", label: "Running", color: "var(--caution)" },
  complete: { tone: "positive", label: "Complete", color: "var(--positive)" },
  failed: { tone: "negative", label: "Failed", color: "var(--negative)" },
  cancelled: { tone: "neutral", label: "Cancelled", color: "var(--ink-4)" },
};

export interface RunAttempt {
  status: RunStatusValue | "idle";
  runId: string | null;
  progress: number;
  error: string | null;
}

/**
 * Two things can be true at once: the run you just submitted failed, and the
 * dashboard is still showing the last run that succeeded. The card keeps them
 * visually separate so a status never appears to belong to the wrong run.
 */
export function RunStatus({
  run,
  attempt,
}: {
  run: RunSummary | null;
  attempt: RunAttempt;
}) {
  const active = attempt.status === "queued" || attempt.status === "running";
  const attemptIsNews = attempt.status !== "idle";
  const headline = attemptIsNews ? attempt.status : (run?.status ?? "idle");
  const style = STATUS_STYLE[headline];

  return (
    <Card>
      <CardHeader
        eyebrow="Run"
        title="Run status"
        actions={
          <Pill tone={style.tone}>
            <Dot color={style.color} className={active ? "breathe" : undefined} />
            {style.label}
          </Pill>
        }
      />

      {attemptIsNews ? (
        <div className="mt-4 rounded-[12px] border border-hairline bg-surface-2 p-3">
          <p className="text-[12px] font-medium text-ink">
            {active
              ? "Current run"
              : attempt.status === "complete"
                ? "Latest live run"
                : `Last attempt ${attempt.status}`}
            {attempt.runId ? (
              <span className="ml-2 font-mono text-[11px] font-normal text-ink-3">
                {attempt.runId}
              </span>
            ) : null}
          </p>

          {active ? (
            <>
              <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-surface-3">
                <div
                  className="h-full rounded-full bg-accent transition-[width] duration-500 [transition-timing-function:var(--ease)]"
                  style={{
                    width: `${Math.max(2, Math.round(attempt.progress * 100))}%`,
                  }}
                />
              </div>
              <p className="mt-2 text-[12px] text-ink-3">
                {attempt.status === "queued"
                  ? "Waiting for the worker\u2026"
                  : `Running live simulator\u2026 about ${Math.round(attempt.progress * 100)}%`}
              </p>
            </>
          ) : null}

          {attempt.status === "complete" ? (
            <p className="mt-2 text-[12px] leading-relaxed text-ink-2">
              Live simulation finished. Headline metrics below are from this run
              (source: live simulator), not the recorded fixture.
            </p>
          ) : null}

          {attempt.error ? (
            <p
              role="alert"
              className="mt-2 rounded-[10px] bg-negative-soft px-2.5 py-2 text-[12px] leading-relaxed text-negative"
            >
              {attempt.error}
            </p>
          ) : null}

          {run && active ? (
            <p className="mt-2 text-[11px] leading-relaxed text-ink-3">
              The results below are still from {run.run_id} and have not changed.
            </p>
          ) : null}
        </div>
      ) : null}

      {run ? (
        <dl className="mt-4 space-y-2.5">
          <Row
            label={attemptIsNews ? "Results shown from" : "Run ID"}
            value={<span className="font-mono text-[12px]">{run.run_id}</span>}
          />
          <Row
            label="Data source"
            value={
              <Pill tone={run.source === "live" ? "positive" : "caution"}>
                {run.source === "live" ? "Live simulator" : "Recorded fixture"}
              </Pill>
            }
          />
          <Row
            label="Scenario"
            value={
              <span className="tabular text-right text-[12px] text-ink-2">
                {formatScenarioValue("temperature", run.scenario.temperature)} &middot;{" "}
                {formatScenarioValue("humidity", run.scenario.humidity)} &middot;{" "}
                {formatScenarioValue("rainfall", run.scenario.rainfall)} &middot;{" "}
                {formatScenarioValue("population", run.scenario.population)}
              </span>
            }
          />
          {run.city ? (
            <Row
              label="City"
              value={
                <span className="text-right text-[12px] text-ink-2">
                  {run.city.name} &middot; {run.city.zones} zones &middot;{" "}
                  {run.city.routes} routes
                </span>
              }
            />
          ) : null}
          {run.before ? (
            <Row
              label="Citizens simulated"
              value={
                <span className="tabular text-[12px] text-ink-2">
                  {run.before.citizen_count.toLocaleString("en-GB")} &middot; up to{" "}
                  {run.city?.rendered_agent_cap ?? 500} rendered
                </span>
              }
            />
          ) : null}
        </dl>
      ) : null}

      {run && run.warnings.length > 0 ? (
        <ul className="mt-4 space-y-2 border-t border-hairline pt-4">
          {run.warnings.map((warning, index) => (
            <li
              key={warning}
              className={cx(
                "flex gap-2 text-[11.5px] leading-relaxed",
                index === 0 ? "text-ink-2" : "text-ink-3",
              )}
            >
              <span aria-hidden className="mt-[3px] text-ink-4">
                &bull;
              </span>
              <span>{warning}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </Card>
  );
}

/**
 * One-line status for the scenario drawer. The full card, with run metadata
 * and warnings, lives in the results panel only; this shows just enough to
 * follow a run you started from the form, and links to the details.
 */
export function RunProgressLine({
  run,
  attempt,
  onShowDetails,
}: {
  run: RunSummary | null;
  attempt: RunAttempt;
  onShowDetails: () => void;
}) {
  const active = attempt.status === "queued" || attempt.status === "running";
  const headline = attempt.status !== "idle" ? attempt.status : (run?.status ?? "idle");
  const style = STATUS_STYLE[headline];
  const pct = Math.round(attempt.progress * 100);

  return (
    <div className="rounded-[12px] border border-hairline bg-surface px-3 py-2.5" aria-live="polite">
      <div className="flex items-center gap-2">
        <Pill tone={style.tone}>
          <Dot color={style.color} className={active ? "breathe" : undefined} />
          {style.label}
        </Pill>
        <span className="min-w-0 truncate font-mono text-[11px] text-ink-3">
          {attempt.runId ?? run?.run_id ?? "No run yet"}
        </span>
        <button
          type="button"
          onClick={onShowDetails}
          className="ml-auto shrink-0 rounded-[8px] px-2 py-1 text-[12px] font-semibold text-accent hover:bg-accent-soft"
        >
          Run details
        </button>
      </div>
      {active ? (
        <>
          <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-surface-3">
            <div
              className="h-full rounded-full bg-accent transition-[width] duration-500 [transition-timing-function:var(--ease)]"
              style={{ width: `${Math.max(2, pct)}%` }}
            />
          </div>
          <p className="mt-1.5 text-[12px] text-ink-3">
            {attempt.status === "queued"
              ? "Waiting for the worker…"
              : `Running live simulator… about ${pct}%`}
          </p>
        </>
      ) : null}
      {attempt.error ? (
        <p
          role="alert"
          className="mt-2 rounded-[10px] bg-negative-soft px-2.5 py-2 text-[12px] leading-relaxed text-negative"
        >
          {attempt.error}
        </p>
      ) : null}
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-[12px] text-ink-3">{label}</dt>
      <dd className="min-w-0 text-right">{value}</dd>
    </div>
  );
}
