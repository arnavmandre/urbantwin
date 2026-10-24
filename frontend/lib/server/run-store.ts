import "server-only";

import { fixtures, RECORDED_RUN_ID } from "./fixtures";
import type {
  ApiErrorBody,
  RunRequest,
  RunStatus,
  RunSummary,
  ScenarioField,
  ScenarioInput,
} from "../types";

/**
 * Mock-mode run lifecycle.
 *
 * There is no job queue, no worker and no run database — see "What has not been
 * built" in the handoff. This store exists so the UI can be developed against
 * the real status machine (queued -> running -> complete | failed | cancelled)
 * and so a second concurrent run is refused the way a single local worker would
 * refuse it.
 *
 * A completed mock run replays the recorded report. It never claims the
 * submitted scenario was simulated: when the inputs differ from the recorded
 * ones, `warnings[0]` says so in plain language and the UI shows it.
 */

const QUEUED_MS = 600;
const RUNNING_MS = 3_400;

interface RunRecord {
  runId: string;
  scenario: ScenarioInput;
  request: RunRequest;
  startedAt: number;
  cancelledAt: number | null;
  forcedFailure: boolean;
}

interface Store {
  runs: Map<string, RunRecord>;
  counter: number;
}

// Route handlers are stateless between requests; the dev server also reloads
// modules. globalThis keeps the store alive across both.
const globalStore = globalThis as unknown as { __urbantwinRuns?: Store };
const store: Store = (globalStore.__urbantwinRuns ??= {
  runs: new Map(),
  counter: 0,
});

// --------------------------------------------------------------------------
// Validation
// --------------------------------------------------------------------------

const FIELDS: ScenarioField[] = ["temperature", "humidity", "rainfall", "population"];

export async function validateScenario(
  body: unknown,
): Promise<{ ok: true; request: RunRequest } | { ok: false; error: ApiErrorBody }> {
  const catalog = await fixtures.scenarios();
  const fields: Partial<Record<ScenarioField, string>> = {};

  if (typeof body !== "object" || body === null) {
    return {
      ok: false,
      error: {
        error: { code: "validation_failed", message: "Expected a JSON scenario object." },
      },
    };
  }
  const raw = body as Record<string, unknown>;

  for (const field of FIELDS) {
    const value = raw[field];
    const [min, max] = catalog.constraints[field];
    if (typeof value !== "number" || !Number.isFinite(value)) {
      fields[field] = "Required numeric value.";
      continue;
    }
    if (value < min || value > max) {
      fields[field] = `Must be between ${min} and ${max}.`;
    }
  }

  if (Object.keys(fields).length > 0) {
    return {
      ok: false,
      error: {
        error: {
          code: "validation_failed",
          message: "Scenario is outside the simulator's accepted input ranges.",
          fields,
        },
      },
    };
  }

  // A recorded run is always a Pune run.
  if (raw.city !== undefined && raw.city !== "pune") {
    return {
      ok: false,
      error: {
        error: {
          code: "validation_failed",
          message: "Only Pune is supported.",
        },
      },
    };
  }

  const request: RunRequest = {
    temperature: raw.temperature as number,
    humidity: raw.humidity as number,
    rainfall: raw.rainfall as number,
    population: raw.population as number,
    apply_recommended_interventions: raw.apply_recommended_interventions !== false,
    selected_recommendation_ids: Array.isArray(raw.selected_recommendation_ids)
      ? raw.selected_recommendation_ids.filter(
          (value): value is import("../types").RecommendationId =>
            value === "increase_shade" ||
            value === "improve_drainage" ||
            value === "alternative_pedestrian_routes" ||
            value === "no_major_intervention",
        )
      : undefined,
    animation_frames: typeof raw.animation_frames === "number" ? raw.animation_frames : 60,
    animation_duration_seconds:
      typeof raw.animation_duration_seconds === "number"
        ? raw.animation_duration_seconds
        : 60,
    debug_force: raw.debug_force === "failed" ? "failed" : undefined,
  };
  return { ok: true, request };
}

// --------------------------------------------------------------------------
// Lifecycle
// --------------------------------------------------------------------------

function statusOf(record: RunRecord): RunStatus {
  if (record.cancelledAt !== null) return "cancelled";
  const elapsed = Date.now() - record.startedAt;
  if (elapsed < QUEUED_MS) return "queued";
  if (elapsed < RUNNING_MS) return "running";
  return record.forcedFailure ? "failed" : "complete";
}

export function activeRunId(): string | null {
  for (const record of store.runs.values()) {
    const status = statusOf(record);
    if (status === "queued" || status === "running") return record.runId;
  }
  return null;
}

export function createRun(request: RunRequest): RunRecord {
  store.counter += 1;
  const runId = `run_mock_${String(store.counter).padStart(3, "0")}`;
  const record: RunRecord = {
    runId,
    scenario: {
      temperature: request.temperature,
      humidity: request.humidity,
      rainfall: request.rainfall,
      population: request.population,
    },
    request,
    startedAt: Date.now(),
    cancelledAt: null,
    forcedFailure: request.debug_force === "failed",
  };
  store.runs.set(runId, record);
  return record;
}

export function cancelRun(runId: string): boolean {
  const record = store.runs.get(runId);
  if (!record) return false;
  const status = statusOf(record);
  if (status !== "queued" && status !== "running") return false;
  record.cancelledAt = Date.now();
  return true;
}

export function progressOf(runId: string): number | null {
  const record = store.runs.get(runId);
  if (!record) return null;
  return Math.min(1, (Date.now() - record.startedAt) / RUNNING_MS);
}

// --------------------------------------------------------------------------
// Resolution
// --------------------------------------------------------------------------

function sameScenario(a: ScenarioInput, b: ScenarioInput): boolean {
  return FIELDS.every((f) => a[f] === b[f]);
}

function describe(s: ScenarioInput): string {
  return `${s.temperature} \u00b0C, ${s.humidity}% humidity, ${s.rainfall} mm rainfall, ${new Intl.NumberFormat(
    "en-GB",
  ).format(s.population)} population equivalent`;
}

/** The recorded run, served as-is. This is the page's initial state. */
export async function recordedRun(): Promise<RunSummary> {
  return fixtures.recordedRun();
}

export async function resolveRun(runId: string): Promise<RunSummary | null> {
  if (runId === RECORDED_RUN_ID) return recordedRun();

  const record = store.runs.get(runId);
  if (!record) return null;

  const status = statusOf(record);
  const recorded = await fixtures.recordedRun();
  const base: RunSummary = {
    run_id: record.runId,
    status,
    source: "recorded_fixture",
    created_utc: new Date(record.startedAt).toISOString(),
    scenario: record.scenario,
    warnings: [],
  };

  if (status === "queued" || status === "running") {
    return {
      ...base,
      warnings: [
        "Mock mode: no simulator process is running. This progress is a timed " +
          "placeholder for the planned job API.",
      ],
    };
  }

  if (status === "cancelled") {
    return {
      ...base,
      warnings: ["Run cancelled before it produced results."],
    };
  }

  if (status === "failed") {
    return {
      ...base,
      error: {
        code: "simulation_failed",
        message:
          "Mock failure requested from the UI state tester. No simulator ran, " +
          "so nothing actually failed.",
      },
      warnings: ["This failure was injected to exercise the error state."],
    };
  }

  const scenarioMatches = sameScenario(record.scenario, recorded.scenario);
  const mismatchWarning = scenarioMatches
    ? "Mock mode: this is the recorded report for exactly these inputs, replayed. No simulator ran for this request."
    : `Mock mode: the recorded report was run at ${describe(
        recorded.scenario,
      )}. Every metric below is that run replayed and does not respond to the inputs you submitted. Point URBANTWIN_API_BASE at the Python API for scenario-specific results.`;

  const applyInterventions = record.request.apply_recommended_interventions;

  return {
    ...recorded,
    run_id: record.runId,
    status: "complete",
    created_utc: base.created_utc,
    // The submitted scenario is echoed so the form and the result cannot
    // silently disagree, but the mismatch warning above carries the truth.
    scenario: record.scenario,
    after: applyInterventions ? recorded.after : undefined,
    delta: applyInterventions ? recorded.delta : undefined,
    intervention: applyInterventions ? recorded.intervention : undefined,
    warnings: [mismatchWarning, ...recorded.warnings],
  };
}
