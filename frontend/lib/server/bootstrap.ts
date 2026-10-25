import "server-only";

import { fixtures } from "./fixtures";
import { recordedRun, resolveRun } from "./run-store";
import { analyticsBase, upstreamBase } from "./upstream";
import type {
  Health,
  ModelCard,
  RunSummary,
  ScenarioCatalog,
  StreamConfig,
} from "../types";

/**
 * Server-side page payload.
 *
 * The dashboard is rendered with data already in hand so the first paint is the
 * real thing rather than a skeleton. In mock mode the fixtures are read from
 * disk; with `URBANTWIN_API_BASE` set the same shapes are fetched from the
 * Python service, and if that service is down the page says the backend is
 * unreachable instead of quietly falling back to recorded numbers.
 */
export interface Bootstrap {
  health: Health;
  scenarios: ScenarioCatalog;
  modelCard: ModelCard;
  streamConfig: StreamConfig;
  run: RunSummary | null;
  /** Set when a configured live backend could not be reached. */
  upstreamError: string | null;
  /** Grafana base URL from URBANTWIN_GRAFANA_URL; null hides the Analytics link. */
  analyticsUrl: string | null;
}

const UNREACHABLE_HEALTH = (base: string, detail: string): Health => ({
  status: "offline",
  mode: "live",
  source: "live",
  checked_utc: new Date().toISOString(),
  simulator: false,
  omniverse_stream: "offline",
  model_card: false,
  capabilities: {
    http_api: false,
    live_simulation: false,
    omniverse_streaming: false,
    llm_advisor: false,
    random_forest_inference: false,
    run_persistence: false,
  },
  notes: [`Configured backend ${base} did not respond: ${detail}`],
});

export async function loadBootstrap(runId?: string): Promise<Bootstrap> {
  return { ...(await loadData(runId)), analyticsUrl: analyticsBase() };
}

async function loadData(runId?: string): Promise<Omit<Bootstrap, "analyticsUrl">> {
  const base = upstreamBase();

  if (!base) {
    const [health, scenarios, modelCard, streamConfig] = await Promise.all([
      fixtures.health(),
      fixtures.scenarios(),
      fixtures.modelCard(),
      fixtures.streamConfig(),
    ]);
    // A run id this dev server no longer holds (e.g. after a restart) falls back to the recorded run.
    const run = (runId ? await resolveRun(runId) : null) ?? (await recordedRun());
    return { health, scenarios, modelCard, streamConfig, run, upstreamError: null };
  }

  try {
    const get = async <T,>(path: string): Promise<T> => {
      const response = await fetch(`${base}${path}`, {
        cache: "no-store",
        signal: AbortSignal.timeout(15_000),
      });
      if (!response.ok) {
        throw Object.assign(new Error(`${path} returned ${response.status}`), { status: response.status });
      }
      return (await response.json()) as T;
    };

    const [health, scenarios, modelCard, streamConfig] = await Promise.all([
      get<Health>("/api/health"),
      get<ScenarioCatalog>("/api/scenarios"),
      get<ModelCard>("/api/model-card"),
      get<StreamConfig>("/api/stream/config"),
    ]);
    // An unknown run id is not a backend outage (404 -> no run).
    // No ?run=: open the newest completed run, the one the published 3D view is showing.
    const wanted =
      runId ?? (await get<{ latest_run_id?: string | null }>("/api/runs")).latest_run_id ?? undefined;
    const run = wanted
      ? await get<RunSummary>(`/api/runs/${encodeURIComponent(wanted)}`).catch((error: unknown) => {
          if ((error as { status?: number }).status === 404) return null;
          throw error;
        })
      : null;
    return { health, scenarios, modelCard, streamConfig, run, upstreamError: null };
  } catch (error) {
    const detail = error instanceof Error ? error.message : "unknown error";
    const [scenarios, modelCard, streamConfig] = await Promise.all([
      fixtures.scenarios(),
      fixtures.modelCard(),
      fixtures.streamConfig(),
    ]);
    return {
      health: UNREACHABLE_HEALTH(base, detail),
      // Constraints, the model card and the stream config are static reference
      // data; the run is not, so nothing is shown in place of live results.
      scenarios,
      modelCard,
      streamConfig: { ...streamConfig, status: "offline" },
      run: null,
      upstreamError: `Configured backend ${base} did not respond: ${detail}`,
    };
  }
}
