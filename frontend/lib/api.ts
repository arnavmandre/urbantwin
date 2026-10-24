/**
 * Browser-side client for the Argus AI web API.
 *
 * Every call goes to this app's own route handlers under `/api`, which either
 * serve the recorded fixtures or forward to the Python service once
 * `URBANTWIN_API_BASE` is configured. Components therefore never need to know
 * which of the two is answering; they read `Health.mode` to decide what they
 * are allowed to claim.
 *
 * Server components must not import this module — they read the fixtures
 * directly through `lib/server/*` so the large payloads stay on the server.
 */
import type {
  ApiErrorBody,
  CitizenPage,
  Health,
  ModelCard,
  RunRequest,
  RunState,
  RunSummary,
  ScenarioCatalog,
  ScenarioField,
  StreamConfig,
  ViewCommand,
  ViewCommandResult,
  ExplainResponse,
  RagAdvisorResponse,
  AdvisorChatResponse,
} from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly code: ApiErrorBody["error"]["code"] | "network_error";
  readonly fields?: Partial<Record<ScenarioField, string>>;

  constructor(
    status: number,
    code: ApiError["code"],
    message: string,
    fields?: ApiError["fields"],
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.fields = fields;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
  } catch (error) {
    throw new ApiError(
      0,
      "network_error",
      error instanceof Error ? error.message : "The request could not be sent.",
    );
  }

  const text = await response.text();
  const body = text ? (JSON.parse(text) as unknown) : null;

  if (!response.ok) {
    const parsed = body as ApiErrorBody | null;
    throw new ApiError(
      response.status,
      parsed?.error?.code ?? "upstream_unavailable",
      parsed?.error?.message ?? `Request failed with status ${response.status}.`,
      parsed?.error?.fields,
    );
  }
  return body as T;
}

export const api = {
  health: () => request<Health>("/health"),
  scenarios: () => request<ScenarioCatalog>("/scenarios"),
  modelCard: () => request<ModelCard>("/model-card"),
  streamConfig: () => request<StreamConfig>("/stream/config"),

  createRun: (body: RunRequest) =>
    request<{ run_id: string; status: RunSummary["status"] }>("/runs", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  run: (runId: string) =>
    request<RunSummary & { progress?: number }>(`/runs/${encodeURIComponent(runId)}`),

  cancelRun: (runId: string) =>
    request<{ run_id: string; status: "cancelled" }>(
      `/runs/${encodeURIComponent(runId)}`,
      { method: "DELETE" },
    ),

  citizens: (runId: string, state: RunState, limit: number, offset: number) =>
    request<CitizenPage>(
      `/runs/${encodeURIComponent(runId)}/citizens?state=${state}&limit=${limit}&offset=${offset}`,
    ),

  view: (runId: string, command: ViewCommand) =>
    request<ViewCommandResult>(`/runs/${encodeURIComponent(runId)}/view`, {
      method: "POST",
      body: JSON.stringify(command),
    }),

  explain: (runId: string) =>
    request<ExplainResponse>(`/runs/${encodeURIComponent(runId)}/explain`, {
      method: "POST",
      body: "{}",
    }),

  advise: (runId: string) =>
    request<RagAdvisorResponse>(`/runs/${encodeURIComponent(runId)}/advise`, {
      method: "POST",
      body: "{}",
    }),

  chat: (runId: string, message: string, sessionId: string | null) =>
    request<AdvisorChatResponse>(`/runs/${encodeURIComponent(runId)}/chat`, {
      method: "POST",
      body: JSON.stringify({ message, session_id: sessionId ?? undefined }),
    }),
};
