"use client";

import { useEffect, useRef, type ReactNode } from "react";

import { Icon } from "@/components/ui/Icon";
import { Dot } from "@/components/ui/Pill";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { cx } from "@/lib/cx";
import {
  HEADLINE_METRICS,
  METRIC_META,
  deltaPolarity,
  formatDelta,
  formatMetric,
} from "@/lib/metric-format";
import type { RunState, RunStatus, RunSummary } from "@/lib/types";

export interface ResultsAttempt {
  status: RunStatus | "idle";
  active: boolean;
}

/**
 * Bottom sheet for the run's results.
 *
 * Collapsed, it is a one-line "peek" of the headline metrics for the state on
 * screen. Expanded, it scrolls its own content so the page itself never does.
 * The body stays mounted while collapsed, so per-run panels keep what they
 * have already fetched.
 */
export function ResultsDrawer({
  run,
  state,
  hasAfter,
  onStateChange,
  attempt,
  upstreamError,
  expanded,
  onExpandedChange,
  onPeekHeight,
  bodyRef,
  children,
}: {
  run: RunSummary | null;
  state: RunState;
  hasAfter: boolean;
  onStateChange: (state: RunState) => void;
  attempt: ResultsAttempt;
  upstreamError: string | null;
  expanded: boolean;
  onExpandedChange: (expanded: boolean) => void;
  /** Reports the collapsed strip's height so floating chrome can sit above it. */
  onPeekHeight: (px: number) => void;
  bodyRef?: React.Ref<HTMLDivElement>;
  children: ReactNode;
}) {
  const peekRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = peekRef.current;
    if (!node) return;
    const report = () => onPeekHeight(Math.ceil(node.getBoundingClientRect().height));
    report();
    const observer = new ResizeObserver(report);
    observer.observe(node);
    return () => observer.disconnect();
  }, [onPeekHeight]);

  const arm = state === "after" && run?.after ? run.after : run?.before;
  const other = state === "after" ? run?.before : run?.after;
  const status = statusLine(run, attempt, upstreamError);

  return (
    <section
      aria-label="Scenario impact"
      className="absolute inset-x-0 bottom-0 z-20 flex flex-col border-t border-hairline bg-surface shadow-[0_-12px_32px_-24px_rgba(0,0,0,0.35)] pb-[env(safe-area-inset-bottom)] sm:rounded-t-[18px]"
    >
      <div
        ref={peekRef}
        className="flex flex-wrap items-center gap-x-4 gap-y-2 px-3 py-2.5 sm:px-5"
      >
        <div className="min-w-0">
          <p className="text-[13px] font-semibold tracking-[-0.01em] text-ink">
            Scenario impact
          </p>
          <p className="flex items-center gap-1.5 text-[11px] text-ink-3">
            <Dot color={status.color} className={attempt.active ? "breathe" : undefined} />
            <span className="truncate">{status.text}</span>
          </p>
        </div>

        {arm ? (
          <dl className="order-last flex w-full min-w-0 gap-4 overflow-x-auto sm:order-none sm:w-auto sm:flex-1 sm:justify-center-safe">
            {HEADLINE_METRICS.map((key, index) => {
              const value = arm.metrics[key];
              const compare = other?.metrics[key];
              const delta =
                compare === undefined ? null : state === "after" ? value - compare : compare - value;
              const polarity = delta === null ? null : deltaPolarity(key, delta);
              return (
                <div key={key} className={cx("shrink-0", index > 1 && "hidden lg:block")}>
                  <dt className="text-[10.5px] font-medium text-ink-3">
                    {METRIC_META[key].label}
                  </dt>
                  <dd className="flex items-baseline gap-1.5">
                    <span className="tabular text-[16px] font-semibold tracking-[-0.02em] text-ink">
                      {formatMetric(key, value)}
                    </span>
                    {delta !== null && polarity ? (
                      <span
                        className={cx(
                          "tabular text-[10.5px] font-semibold",
                          polarity === "improvement"
                            ? "text-positive"
                            : polarity === "regression"
                              ? "text-negative"
                              : "text-ink-3",
                        )}
                        title={
                          state === "after"
                            ? "Change from before to after the intervention"
                            : "Change the intervention would make"
                        }
                      >
                        {formatDelta(key, delta)}
                      </span>
                    ) : null}
                  </dd>
                </div>
              );
            })}
          </dl>
        ) : (
          <p className="text-[12px] text-ink-3 sm:flex-1">
            {upstreamError
              ? "No results: the configured backend is unreachable."
              : "No results yet. Open Scenario and run a simulation."}
          </p>
        )}

        <div className="ml-auto flex items-center gap-2">
          {run?.before ? (
            <div className="flex flex-col items-end">
              <SegmentedControl<RunState>
                ariaLabel="Metric state"
                size="sm"
                value={state}
                onChange={onStateChange}
                segments={[
                  { value: "before", label: "Before" },
                  {
                    value: "after",
                    label: "After",
                    disabled: !hasAfter,
                    title: hasAfter ? undefined : "This run has no intervention arm.",
                  },
                ]}
              />
              {!hasAfter ? (
                <span className="mt-0.5 text-[10px] text-ink-3">No intervention arm</span>
              ) : null}
            </div>
          ) : null}
          <button
            type="button"
            aria-expanded={expanded}
            aria-controls="results-body"
            onClick={() => onExpandedChange(!expanded)}
            className="flex items-center gap-1.5 rounded-[10px] border border-hairline px-2.5 py-1.5 text-[12px] font-semibold text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink"
          >
            <Icon name={expanded ? "chevron-down" : "chevron-up"} />
            <span>{expanded ? "Back to city" : "Details"}</span>
          </button>
        </div>
      </div>

      <div
        id="results-body"
        ref={bodyRef}
        hidden={!expanded}
        className="max-h-[calc(100dvh-11rem)] overflow-y-auto overscroll-contain border-t border-hairline bg-canvas px-3 py-4 sm:max-h-[min(62dvh,680px)] sm:px-5"
      >
        <div className="mx-auto flex max-w-[1200px] flex-col gap-4">{children}</div>
      </div>
    </section>
  );
}

function statusLine(
  run: RunSummary | null,
  attempt: ResultsAttempt,
  upstreamError: string | null,
): { text: string; color: string } {
  if (upstreamError) {
    return { text: "Backend unreachable", color: "var(--negative)" };
  }
  const source = run ? (run.source === "live" ? "live simulator" : "recorded fixture") : null;
  if (attempt.active) {
    return {
      text: run
        ? `Run in progress · still showing ${run.run_id}`
        : "Run in progress",
      color: "var(--caution)",
    };
  }
  if (attempt.status === "failed" || attempt.status === "cancelled") {
    return {
      text: run
        ? `Last run ${attempt.status} · showing earlier ${run.run_id}`
        : `Last run ${attempt.status}`,
      color: attempt.status === "failed" ? "var(--negative)" : "var(--ink-4)",
    };
  }
  if (!run) return { text: "Idle", color: "var(--ink-4)" };
  return {
    text: `${run.run_id} · ${source}`,
    color: run.source === "live" ? "var(--positive)" : "var(--caution)",
  };
}

