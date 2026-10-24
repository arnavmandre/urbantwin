import "server-only";

import { readFile } from "node:fs/promises";
import path from "node:path";

import type {
  CitizenResult,
  Health,
  ModelCard,
  RunState,
  RunSummary,
  ScenarioCatalog,
  StreamConfig,
} from "../types";

/**
 * Reads the recorded API fixtures in `frontend/mocks/`.
 *
 * These are exported from the real simulator report by
 * `integration/export_api_mocks.py`. They are read on the server only: the
 * citizen fixture alone is ~220 KB and the handoff forbids parsing the large
 * report inside a React component. Route handlers slice it before it is sent.
 */

const MOCK_DIR = path.join(process.cwd(), "mocks");

const cache = new Map<string, unknown>();

async function load<T>(relativePath: string): Promise<T> {
  const cached = cache.get(relativePath);
  if (cached) return cached as T;
  const raw = await readFile(path.join(MOCK_DIR, relativePath), "utf8");
  const parsed = JSON.parse(raw) as T;
  // Fixtures are immutable build artifacts, so caching them is safe.
  cache.set(relativePath, parsed);
  return parsed;
}

export interface CitizenFixture {
  run_id: string;
  source: "recorded_fixture";
  created_utc: string;
  states: Record<
    RunState,
    { items: CitizenResult[]; total_in_run: number; included_in_fixture: number }
  >;
}

export const RECORDED_RUN_ID = "run_pune_recorded";

export const fixtures = {
  health: () => load<Health>("health.json"),
  scenarios: () => load<ScenarioCatalog>("scenarios.json"),
  streamConfig: () => load<StreamConfig>("stream-config.json"),
  modelCard: () => load<ModelCard>("model-card.json"),
  recordedRun: () => load<RunSummary>(`runs/${RECORDED_RUN_ID}.json`),
  citizens: () => load<CitizenFixture>(`runs/${RECORDED_RUN_ID}.citizens.json`),
};
