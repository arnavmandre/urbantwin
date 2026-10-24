"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";

import { AdvisorPanel } from "@/components/AdvisorPanel";
import { AdvisorImpactSummary } from "@/components/AdvisorImpactSummary";
import { RunExplainPanel } from "@/components/RunExplainPanel";
import { RagAdvisorPanel } from "@/components/RagAdvisorPanel";
import { BeforeAfterChart } from "@/components/BeforeAfterChart";
import { BehaviorLegend } from "@/components/BehaviorLegend";
import { CitizenInspector } from "@/components/CitizenInspector";
import { Disclosures } from "@/components/Disclosures";
import { MetricGrid } from "@/components/MetricGrid";
import { ProblemAreas } from "@/components/ProblemAreas";
import { ResultsDrawer, ResultsSection } from "@/components/ResultsDrawer";
import { RunProgressLine, RunStatus } from "@/components/RunStatus";
import { ScenarioControls } from "@/components/ScenarioControls";
import { ScenarioDrawer } from "@/components/ScenarioDrawer";
import { SiteHeader } from "@/components/SiteHeader";
import { Card, CardHeader } from "@/components/ui/Card";
import { Icon } from "@/components/ui/Icon";
import { Pill } from "@/components/ui/Pill";
import { cx } from "@/lib/cx";
import type { Bootstrap } from "@/lib/server/bootstrap";
import { useRunner } from "@/lib/use-runner";
import type { CityKey, RunState, RunSummary, ScenarioInput } from "@/lib/types";
import type { ViewerState } from "@/lib/viewer";

/**
 * The viewport is client-only: WebRTC and media APIs do not exist during server
 * rendering, and the adapter must never run on the server.
 */
const OmniverseViewer = dynamic(
  () => import("@/components/OmniverseViewer").then((m) => m.OmniverseViewer),
  {
    ssr: false,
    loading: () => <div className="shimmer size-full" />,
  },
);

/**
 * Immersive workspace: the Kit viewport fills everything under the header,
 * and the scenario form and the results float over it in two drawers.
 *
 * The viewer is rendered once, at a fixed position in the tree, and the
 * drawers are its siblings. Opening, closing or resizing them never remounts
 * it, so the WebRTC session survives every layout change.
 */
export function Dashboard({ bootstrap }: { bootstrap: Bootstrap }) {
  const { health, scenarios, streamConfig } = bootstrap;

  const [run, setRun] = useState<RunSummary | null>(bootstrap.run);
  const [state, setState] = useState<RunState>("before");
  const [scenario, setScenario] = useState<ScenarioInput>(
    bootstrap.run?.scenario ??
      scenarios.presets[scenarios.presets.length - 1] ?? {
        temperature: 26,
        humidity: 40,
        rainfall: 5,
        population: 30000,
      },
  );
  const [applyInterventions, setApplyInterventions] = useState(true);
  const streamCity: CityKey | null =
    streamConfig.status === "available" ? streamConfig.city ?? "london" : null;
  // Start on the city the last run or the stream is about, so results and viewport agree.
  const [city, setCity] = useState<CityKey>(
    bootstrap.run?.city?.key ?? streamCity ?? "london",
  );
  const impactRef = useRef<HTMLDivElement>(null);
  const revealImpactAfterRun = useRef(false);
  const [scrollToImpact, setScrollToImpact] = useState(false);

  const [scenarioOpen, setScenarioOpen] = useState(false);
  const [resultsOpen, setResultsOpen] = useState(false);
  const [peekHeight, setPeekHeight] = useState(64);
  const [viewerStatus, setViewerStatus] = useState<ViewerState["status"]>("idle");
  const [aboutOpen, setAboutOpen] = useState(false);
  const scenarioButtonRef = useRef<HTMLButtonElement>(null);

  const onComplete = useCallback((summary: RunSummary) => {
    setRun(summary);
    if (revealImpactAfterRun.current) {
      revealImpactAfterRun.current = false;
      setState("after");
      setResultsOpen(true);
      setScrollToImpact(true);
    }
  }, []);
  const runner = useRunner(onComplete);

  const hasAfter = Boolean(run?.after);
  // Derived rather than corrected in an effect: a run without an intervention
  // arm can only ever show "before".
  const shown: RunState = hasAfter ? state : "before";

  const arm = shown === "after" && run?.after ? run.after : run?.before;
  const other = shown === "after" ? run?.before : run?.after;

  useEffect(() => {
    if (!scrollToImpact || !run?.after || !resultsOpen || !impactRef.current) return;
    impactRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    setScrollToImpact(false);
  }, [resultsOpen, run, scrollToImpact]);

  const closeScenario = useCallback(() => {
    setScenarioOpen(false);
    scenarioButtonRef.current?.focus({ preventScroll: true });
  }, []);

  // Escape closes the topmost panel. Controls that own their own popovers
  // (the layers menu) mark the event handled first.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      if (aboutOpen) setAboutOpen(false);
      else if (scenarioOpen) closeScenario();
      else if (resultsOpen) setResultsOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [aboutOpen, closeScenario, resultsOpen, scenarioOpen]);

  const submit = useCallback(
    (options?: {
      forceApply?: boolean;
      debugFail?: boolean;
      selectedRecommendationIds?: import("@/lib/types").RecommendationId[];
    }) => {
      const apply = options?.forceApply ?? applyInterventions;
      if (options?.forceApply) setApplyInterventions(true);
      if (options?.selectedRecommendationIds?.length) {
        revealImpactAfterRun.current = true;
      }
      void runner.start({
        ...scenario,
        city,
        apply_recommended_interventions: apply,
        selected_recommendation_ids: options?.selectedRecommendationIds,
        animation_frames: 12,
        animation_duration_seconds: 12,
        debug_force: options?.debugFail ? "failed" : undefined,
      });
    },
    [applyInterventions, city, runner, scenario],
  );

  const attempt = {
    status: runner.state.status,
    runId: runner.state.runId,
    progress: runner.state.progress,
    error: runner.state.status === "failed" ? runner.state.error : null,
  };

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-canvas">
      <SiteHeader
        health={health}
        viewerStatus={viewerStatus}
        sceneLabel={run?.city?.name ?? streamConfig.stage}
        aboutOpen={aboutOpen}
        onAboutOpenChange={setAboutOpen}
        analyticsHref={analyticsHref(bootstrap.analyticsUrl, run)}
        about={
          <Disclosures
            health={health}
            city={run?.city}
            stage={run?.artifacts?.omniverse_stage}
          />
        }
      />

      <main className="relative min-h-0 flex-1 overflow-hidden">
        <div className="absolute inset-0">
          <OmniverseViewer
            runId={run?.run_id ?? null}
            config={streamConfig}
            state={shown}
            onStateChange={setState}
            hasAfter={hasAfter}
            onStatusChange={setViewerStatus}
            bottomInset={peekHeight}
            topRight={
              <button
                ref={scenarioButtonRef}
                type="button"
                aria-expanded={scenarioOpen}
                aria-controls="scenario-drawer"
                onClick={() => (scenarioOpen ? closeScenario() : setScenarioOpen(true))}
                className="flex items-center gap-2 rounded-[12px] bg-accent px-3 py-2 text-[13px] font-semibold text-accent-ink shadow-[var(--shadow-card)] transition-colors hover:bg-accent-hover"
              >
                <Icon name="sliders" />
                Scenario
                {runner.active ? (
                  <span aria-label="Run in progress" className="breathe size-2 rounded-full bg-accent-ink" />
                ) : null}
              </button>
            }
          />
        </div>

        <ScenarioDrawer open={scenarioOpen} onClose={closeScenario} bottomInset={peekHeight}>
          <ScenarioControls
            plain
            city={city}
            onCityChange={setCity}
            puneAvailable={health.mode === "live"}
            streamCity={streamCity}
            catalog={scenarios}
            scenario={scenario}
            onScenarioChange={setScenario}
            applyInterventions={applyInterventions}
            onApplyInterventionsChange={setApplyInterventions}
            onRun={() => submit()}
            onCancel={() => void runner.cancel()}
            busy={runner.active}
            fieldErrors={runner.state.fieldErrors}
            formError={
              runner.state.status === "failed" ? null : runner.state.error
            }
          />
          <RunProgressLine
            run={run}
            attempt={attempt}
            onShowDetails={() => {
              setResultsOpen(true);
              closeScenario();
            }}
            onReset={runner.reset}
          />
        </ScenarioDrawer>

        <ResultsDrawer
          run={run}
          state={shown}
          hasAfter={hasAfter}
          onStateChange={setState}
          attempt={{ status: runner.state.status, active: runner.active }}
          upstreamError={bootstrap.upstreamError}
          expanded={resultsOpen}
          onExpandedChange={setResultsOpen}
          onPeekHeight={setPeekHeight}
          onOpenScenario={() => setScenarioOpen(true)}
        >
          {bootstrap.upstreamError ? (
            <Card className="border-[color:var(--negative)]/40 bg-negative-soft">
              <CardHeader
                eyebrow="Backend"
                title="The configured backend is unreachable"
                description={bootstrap.upstreamError}
              />
              <p className="mt-3 text-[12px] leading-relaxed text-ink-2">
                No results are shown, because showing recorded numbers here would
                misrepresent them as live output.
              </p>
            </Card>
          ) : null}

          {run && arm ? (
            <Card>
              <CardHeader
                eyebrow="Human impact"
                title="Headline metrics"
                description="Population-weighted results for the state shown in the viewport."
                actions={
                  <Pill tone={shown === "after" ? "accent" : "neutral"}>
                    {shown === "after" ? "After intervention" : "Before (baseline)"}
                  </Pill>
                }
              />
              <MetricGrid
                className="mt-5 lg:grid-cols-4"
                metrics={arm.metrics}
                comparison={other?.metrics}
                state={shown}
              />
            </Card>
          ) : null}

          {run && run.before ? (
            <>
              {run.after && Object.keys(run.intervention ?? {}).length > 0 ? (
                <div ref={impactRef} className="scroll-mt-4">
                  <AdvisorImpactSummary
                    before={run.before.metrics}
                    after={run.after.metrics}
                    intervention={run.intervention ?? {}}
                  />
                </div>
              ) : null}
              <BeforeAfterChart
                before={run.before.metrics}
                after={run.after?.metrics}
                interventionLabel={interventionLabel(run)}
              />
            </>
          ) : null}

          {/* The one detailed status section; the drawer shows a single line.
              Opens by itself while a run is active or after it failed. */}
          {run || attempt.status !== "idle" ? (
            <ResultsSection
              title="Run details"
              open={attempt.status !== "idle" && attempt.status !== "complete"}
              meta={<span className="font-mono">{attempt.runId ?? run?.run_id}</span>}
            >
              <RunStatus run={run} attempt={attempt} />
            </ResultsSection>
          ) : null}

          {run && run.before ? (
            <>
              <ResultsSection
                title="Behaviour and pressure points"
                meta={`${run.before.problem_buildings.length} flagged buildings`}
              >
                <BehaviorLegend
                  before={run.before.behavior_counts}
                  after={run.after?.behavior_counts}
                />
                {arm ? <ProblemAreas summary={arm} state={shown} /> : null}
              </ResultsSection>

              {(health.mode === "live" && run.status === "complete") || run.advisor ? (
                <ResultsSection title="Advisor and calculation details">
                  {health.mode === "live" && run.status === "complete" ? (
                    <>
                      <RagAdvisorPanel
                        key={`rag-${run.run_id}`}
                        runId={run.run_id}
                        busy={runner.active}
                        onApplySelected={(selectedRecommendationIds) =>
                          submit({ forceApply: true, selectedRecommendationIds })
                        }
                      />
                      <RunExplainPanel runId={run.run_id} />
                    </>
                  ) : null}
                  {run.advisor ? (
                    <div>
                      <p className="mb-3 text-[12px] leading-relaxed text-ink-3">
                        These deterministic rules convert selected AI actions into executable simulator parameters and identify affected locations.
                      </p>
                      <AdvisorPanel
                        advisor={run.advisor}
                        source={run.advisor_source}
                        applied={run.intervention}
                        canApply={!runner.active}
                        onApplyRecommended={() => submit({ forceApply: true })}
                      />
                    </div>
                  ) : null}
                </ResultsSection>
              ) : null}

              <ResultsSection
                title="Citizens"
                meta={`${run.before.citizen_count.toLocaleString("en-GB")} simulated`}
              >
                <CitizenInspector
                  key={`${run.run_id}-${shown}`}
                  runId={run.run_id}
                  state={shown}
                  hasAfter={hasAfter}
                />
              </ResultsSection>
            </>
          ) : null}

          <ResultsSection title="Methodology and limitations">
            <p className="text-[12px] leading-relaxed text-ink-2">
              Every figure here is a heuristic prototype estimate from synthetic,
              survey-calibrated citizens, not a medical, meteorological, hydraulic
              or engineering prediction. The full statement of what this prototype
              is, what it is not and where the numbers come from is in About &amp;
              status.{" "}
              <button
                type="button"
                onClick={() => setAboutOpen(true)}
                className="font-semibold text-accent underline-offset-2 hover:underline"
              >
                What this prototype is and is not
              </button>
            </p>
          </ResultsSection>

          {health.mode === "mock" ? (
            <StateTester
              busy={runner.active}
              onFail={() => submit({ debugFail: true })}
              onCancelMidRun={() => {
                submit();
                setTimeout(() => void runner.cancel(), 900);
              }}
            />
          ) : null}
        </ResultsDrawer>

        {/* Dim the city behind an expanded sheet on small screens only, where
            the sheet covers most of it anyway; tapping returns to the city. */}
        <button
          type="button"
          tabIndex={-1}
          aria-hidden
          onClick={() => setResultsOpen(false)}
          className={cx(
            "absolute inset-0 z-10 bg-black/20 transition-opacity sm:hidden",
            resultsOpen ? "opacity-100" : "pointer-events-none opacity-0",
          )}
        />
      </main>
    </div>
  );
}

/**
 * Deep link into the Grafana dashboard, focused on the run on screen. Only a
 * completed live run is passed: it is the only kind the importer has stored.
 */
function analyticsHref(base: string | null, run: RunSummary | null): string | null {
  if (!base) return null;
  const url = `${base}/d/argus-observatory/argus-urban-risk-observatory?orgId=1`;
  return run?.source === "live" && run.status === "complete"
    ? `${url}&var-run=${encodeURIComponent(run.run_id)}`
    : url;
}

function interventionLabel(run: RunSummary): string | null {
  const entries = Object.entries(run.intervention ?? {});
  if (entries.length === 0) return null;
  return `Intervention: ${entries
    .map(([key, value]) => `${key.replaceAll("_", " ")} +${Math.round(value * 100)}%`)
    .join(", ")}.`;
}

/**
 * Developer control for the states that cannot occur against recorded fixtures.
 * Shown only in mock mode and labelled as an injection, never as a real failure.
 */
function StateTester({
  busy,
  onFail,
  onCancelMidRun,
}: {
  busy: boolean;
  onFail: () => void;
  onCancelMidRun: () => void;
}) {
  return (
    <div className="mt-5 flex flex-wrap items-center gap-3 rounded-[14px] border border-dashed border-hairline px-4 py-3 xl:mt-6">
      <Pill tone="neutral">Mock mode only</Pill>
      <p className="text-[11px] text-ink-3">
        Inject terminal run states to check the UI handles them. Nothing is
        simulated and no failure is real.
      </p>
      <div className="ml-auto flex gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={onFail}
          className="rounded-full border border-hairline px-3 py-1 text-[11px] font-semibold text-ink-2 transition-colors hover:text-ink disabled:opacity-40"
        >
          Inject failed run
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={onCancelMidRun}
          className="rounded-full border border-hairline px-3 py-1 text-[11px] font-semibold text-ink-2 transition-colors hover:text-ink disabled:opacity-40"
        >
          Cancel mid-run
        </button>
      </div>
    </div>
  );
}
