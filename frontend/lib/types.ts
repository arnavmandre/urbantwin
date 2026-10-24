/**
 * Types for the Argus AI web API.
 *
 * Source of truth: docs/FRONTEND_BACKEND_HANDOFF.md ("Proposed HTTP API —
 * planned, not implemented"). The Python service does not exist yet; these
 * types describe the contract the frontend is written against and that
 * `frontend/mocks/` currently satisfies.
 *
 * Fields marked EXTENSION are not in the proposed contract. They exist so the
 * UI can tell recorded fixtures apart from a live backend, which the handoff
 * requires ("No backend, streaming or model capability is presented as live
 * unless its health/config endpoint confirms it"). A real backend should
 * implement them too, or the UI degrades to treating the data as unverified.
 */

/** EXTENSION: how a payload was produced. */
export type PayloadSource = "recorded_fixture" | "live";

// --------------------------------------------------------------------------
// Scenario
// --------------------------------------------------------------------------

export interface ScenarioInput {
  temperature: number;
  humidity: number;
  rainfall: number;
  population: number;
}

export type ScenarioField = keyof ScenarioInput;

export interface ScenarioPreset extends ScenarioInput {
  id: string;
  label?: string;
  description?: string;
}

export interface ScenarioCatalog {
  source: PayloadSource;
  constraints: Record<ScenarioField, [number, number]>;
  units: Record<ScenarioField, string>;
  presets: ScenarioPreset[];
  /** EXTENSION: the scenario the recorded fixture was actually run at. */
  recorded_scenario?: ScenarioInput & { run_id: string };
}

/** EXTENSION: which city a run targets (integration/cities.py). Omitted = London. */
export type CityKey = "london" | "pune";

export interface RunRequest extends ScenarioInput {
  city?: CityKey;
  apply_recommended_interventions: boolean;
  selected_recommendation_ids?: RecommendationId[];
  animation_frames?: number;
  animation_duration_seconds?: number;
  /** EXTENSION, mock mode only: force a terminal state to exercise the UI. */
  debug_force?: "failed";
}

// --------------------------------------------------------------------------
// Metrics
// --------------------------------------------------------------------------

export interface SimulationMetrics {
  heat_stress: number; // 0..100, higher is worse
  cold_stress: number; // 0..100, higher is worse
  rain_impact: number; // 0..100, higher is worse
  crowding: number; // 0..100, higher is worse
  safety: number; // 0..100, higher is better
  mobility: number; // 0..100, higher is better
  comfort: number; // city-level, 0..100, higher is better
  citizen_comfort: number; // population-weighted, higher is better
  mean_travel_minutes: number;
  human_experience_index: number; // 0..100, higher is better
}

export type MetricKey = keyof SimulationMetrics;

// --------------------------------------------------------------------------
// Citizens
// --------------------------------------------------------------------------

export type CitizenBehavior =
  | "CONTINUE"
  | "STRESSED"
  | "SEEK_SHADE"
  | "SEEK_SHELTER"
  | "REROUTE"
  | "AVOID_AREA";

export interface CitizenResult {
  id: string;
  archetype: string;
  home: string;
  destination: string;
  route: string;
  travel_minutes: number;
  heat_exposure: number; // 0..100
  cold_exposure: number; // 0..100
  rain_exposure: number; // 0..100
  flood_risk: number; // 0..100
  crowd_exposure: number; // 0..100
  destination_crowding: number; // 0..100
  comfort: number; // 0..100, higher is better
  stress: number; // 0..100, higher is worse
  behavior: CitizenBehavior;
  route_cost: number;
}

export type BehaviorCounts = Record<CitizenBehavior, number>;

export interface CitizenPage {
  run_id: string;
  state: RunState;
  source: PayloadSource;
  limit: number;
  offset: number;
  /** Records this endpoint can serve. In mock mode this is the fixture slice. */
  total: number;
  /** Citizens the simulator actually ran. */
  total_in_run: number;
  items: CitizenResult[];
  notes: string[];
}

// --------------------------------------------------------------------------
// Spatial problems
// --------------------------------------------------------------------------

export interface ProblemBuilding {
  id: string;
  name: string;
  zone: string;
  issues: string[];
  severity: number; // 0..100
}

export interface ProblemRoute {
  id: string;
  from: string;
  to: string;
  via_zones: string[];
  crowding: number;
}

// --------------------------------------------------------------------------
// Advisor
// --------------------------------------------------------------------------

export type RecommendationId =
  | "increase_shade"
  | "improve_drainage"
  | "alternative_pedestrian_routes"
  | "no_major_intervention";

export interface SupportedIntervention {
  changes: Record<string, number>;
  effect: string;
}

export interface AdvisorResult {
  summary: string;
  problem_zones: string[];
  problem_buildings: ProblemBuilding[];
  problem_routes: ProblemRoute[];
  recommendations: RecommendationId[];
  affected_buildings: Record<string, string[]>;
  explanation: string[];
  supported_interventions: Record<string, SupportedIntervention>;
}

export interface InterventionParameters {
  shade_boost?: number;
  drainage_boost?: number;
  route_capacity_boost?: number;
}

/** EXTENSION: lets the UI label the advisor honestly instead of saying "AI". */
export interface AdvisorSource {
  kind: "deterministic_rules" | "llm" | "hybrid";
  label: string;
  detail: string;
}

// --------------------------------------------------------------------------
// Runs
// --------------------------------------------------------------------------

export type RunStatus =
  | "queued"
  | "running"
  | "complete"
  | "failed"
  | "cancelled";

/** Which arm of a run: before the intervention, or after it. */
export type RunState = "before" | "after";

export interface RunStateSummary {
  metrics: SimulationMetrics;
  behavior_counts: BehaviorCounts;
  problem_zones: string[];
  problem_buildings: ProblemBuilding[];
  problem_routes: ProblemRoute[];
  /** EXTENSION: citizens simulated in this arm. */
  citizen_count: number;
  /** EXTENSION: intervention parameters in force for this arm. */
  interventions: Record<string, number>;
}

/** EXTENSION: the calm-weather control arm the simulator reports alongside a run. */
export interface ControlReference {
  scenario: ScenarioInput;
  metrics: SimulationMetrics;
  recommendations: RecommendationId[];
}

/** EXTENSION: what the simulated and rendered city actually contains. */
export interface CityFacts {
  /** EXTENSION: absent on older fixtures, which are all London. */
  key?: CityKey;
  name: string;
  source: string;
  zones: number;
  simulation_buildings: number;
  routes: number;
  visual_buildings: number;
  visual_trees: number;
  rendered_agent_cap: number;
  /** EXTENSION: city-specific "what it is not" statements from the backend. */
  limitations?: string[];
}

export interface RunSummary {
  run_id: string;
  status: RunStatus;
  source: PayloadSource;
  created_utc: string;
  /** 0..1 while queued/running; 1 when complete. Live API now includes this. */
  progress?: number;
  scenario: ScenarioInput;
  before?: RunStateSummary;
  advisor?: AdvisorResult;
  intervention?: InterventionParameters;
  after?: RunStateSummary;
  delta?: Partial<Record<MetricKey, number>>;
  control_reference?: ControlReference;
  city?: CityFacts;
  artifacts?: {
    omniverse_stage: string;
    /** Null for Pune, which has no canonical snapshots. */
    snapshot_pattern: string | null;
  };
  advisor_source?: AdvisorSource;
  warnings: string[];
  /** Present only when `status` is "failed". */
  error?: { code: string; message: string };
}

// --------------------------------------------------------------------------
// Health, streaming, model card
// --------------------------------------------------------------------------

export interface HealthCapabilities {
  http_api: boolean;
  live_simulation: boolean;
  omniverse_streaming: boolean;
  llm_advisor: boolean;
  random_forest_inference: boolean;
  run_persistence: boolean;
}

export interface Health {
  status: "ready" | "degraded" | "mock" | "offline";
  /** EXTENSION: "mock" means every number on screen is a recorded fixture. */
  mode: "live" | "mock";
  source: PayloadSource;
  checked_utc: string;
  simulator: boolean;
  omniverse_stream: "online" | "offline" | "connecting";
  model_card: boolean;
  capabilities: HealthCapabilities;
  notes: string[];
}

export interface StreamConfig {
  status: "offline" | "available";
  source: PayloadSource;
  checked_utc: string;
  /** Null until a streaming-enabled Kit app and session manager exist. */
  signaling_url: string | null;
  /** EXTENSION: DIRECT Kit host/ports for local AppStreamer. */
  signaling_host?: string | null;
  signaling_port?: number | null;
  media_host?: string | null;
  media_port?: number | null;
  ice_servers: RTCIceServerLike[];
  session_token: string | null;
  stage: string;
  /** EXTENSION: the city Kit was launched on (demo_launch.ps1 -City). Absent = London. */
  city?: CityKey;
  reason?: string;
  desktop_fallback?: string;
  references?: string[];
}

/** Structural mirror of RTCIceServer; avoids a DOM lib dependency in shared code. */
export interface RTCIceServerLike {
  urls: string | string[];
  username?: string;
  credential?: string;
}

export type TrustVerdict =
  | "promising"
  | "supported_for_prototype"
  | "not_validated";

export interface ModelEntry {
  target: string;
  kind: "regression" | "classification";
  trust_verdict: TrustVerdict;
  labelled_rows: number;
  final_holdout_rows: number;
  final_holdout: { mae?: number; r2?: number; balanced_accuracy?: number; macro_f1?: number };
  final_holdout_baseline: { mae?: number; r2?: number; balanced_accuracy?: number; macro_f1?: number };
  beats_baseline: boolean;
  beats_shuffled_labels: boolean;
  observed_classes?: string[];
}

export interface ModelCard {
  source: PayloadSource;
  exported_utc: string;
  created_utc: string;
  sklearn_version: string;
  random_seed: number;
  split_policy: string;
  overall_verdict: string;
  limitations: string[];
  models: ModelEntry[];
  wired_into_simulator: boolean;
  survey: {
    participants: number;
    scenario_response_rows: number;
    synthetic_citizens: number;
    holdout_people: number;
    note: string;
  };
}

// --------------------------------------------------------------------------
// View commands (allow-listed; forwarded to Kit messaging when it exists)
// --------------------------------------------------------------------------

export const VIEW_CAMERAS = ["Overview", "Street", "ProblemZone", "Aerial"] as const;
export const VIEW_OVERLAYS = ["behavior", "congestion", "shade", "none"] as const;
export const VIEW_PLAYBACK = ["play", "pause", "restart"] as const;

export type ViewCamera = (typeof VIEW_CAMERAS)[number];
export type ViewOverlay = (typeof VIEW_OVERLAYS)[number];
export type ViewPlayback = (typeof VIEW_PLAYBACK)[number];

export interface ViewCommand {
  state: RunState;
  camera: ViewCamera;
  overlay: ViewOverlay;
  playback: ViewPlayback;
}

export interface ViewCommandResult {
  accepted: boolean;
  delivered: boolean;
  /** Present when accepted; API authorizes, browser delivers over WebRTC. */
  delivery?: "webrtc_client";
  reason?: string;
  command: ViewCommand;
}

// --------------------------------------------------------------------------
// Constrained LLM explanation (Phase 16)
// --------------------------------------------------------------------------

export type ExplainSource = "deterministic" | "llm";

export interface ExplainResponse {
  run_id: string;
  source: ExplainSource;
  text: string;
  claims: string[];
  /** Present when an LLM was configured but fell back to the template. */
  unavailable_reason?: string;
}

// --------------------------------------------------------------------------
// Retrieval-grounded advisor (live API only)
// --------------------------------------------------------------------------

export interface RetrievedKnowledge {
  knowledge_id: string;
  similarity_score: number;
  problem_category: string;
  intervention: string;
  description: string;
  argus_recommendation_id: RecommendationId;
  target_metrics: string[];
  tradeoffs: string[];
  source: { title: string; url: string; status: "VERIFIED" | "NEEDS_SOURCE" };
}

export interface RagRecommendation {
  rank: number;
  argus_recommendation_id: RecommendationId;
  testable: true;
  knowledge_id?: string;
  intervention?: string;
  reason?: string;
  target_metrics?: string[];
  tradeoffs?: string[];
  source?: RetrievedKnowledge["source"];
}

export interface RagAdvisorResponse {
  run_id: string;
  source: "rag_llm" | "deterministic";
  advisor_mode: "rag_llm" | "deterministic_fallback";
  fallback_used: boolean;
  model?: string;
  retrieval_backend?: "faiss_minilm" | "lexical_fallback" | string;
  knowledge_hash?: string;
  unavailable_reason?: string;
  primary_problem?: {
    category: string;
    severity: "low" | "moderate" | "high" | "unknown";
    target_id: string | null;
    evidence: string[];
  };
  recommendations: RagRecommendation[];
  retrieved_knowledge: RetrievedKnowledge[];
}

/** POST /api/runs/{id}/chat. Proposals are already validated against the executable actions. */
export interface AdvisorChatResponse {
  run_id: string;
  source: "agent37" | "deterministic";
  model?: string;
  reply: string;
  proposals: { action: RecommendationId; reason: string }[];
  /** Continue the conversation with this; null on the deterministic fallback. */
  session_id: string | null;
  unavailable_reason?: string;
}

// --------------------------------------------------------------------------
// Errors
// --------------------------------------------------------------------------

export interface ApiErrorBody {
  error: {
    code:
      | "validation_failed"
      | "not_found"
      | "simulation_failed"
      | "upstream_unavailable"
      | "conflict";
    message: string;
    fields?: Partial<Record<ScenarioField, string>>;
  };
}
