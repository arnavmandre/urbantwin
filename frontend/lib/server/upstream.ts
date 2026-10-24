import "server-only";

/**
 * Swap point between recorded fixtures and the Phase 12 Python API.
 *
 * Default (no env): every route handler serves fixtures and labels them
 * `mode: "mock"`. Set `URBANTWIN_API_BASE` (e.g. http://127.0.0.1:8000) and the
 * same handlers forward to `python -m api`. See docs/PHASE12_LOCAL_API.md.
 *
 * Deliberately there is no fallback from live to mock: if the configured
 * backend is unreachable the client gets 502 `upstream_unavailable`. Silently
 * serving a recorded run while claiming to be live is exactly the failure this
 * project is not allowed to have.
 */

export function upstreamBase(): string | null {
  const base = process.env.URBANTWIN_API_BASE?.trim();
  return base ? base.replace(/\/+$/, "") : null;
}

/**
 * Grafana run-history dashboard (analytics/, see docs/PHASE18_GRAFANA_ANALYTICS.md).
 * Unset means no Analytics link: the dashboard only exists when that stack runs.
 */
export function analyticsBase(): string | null {
  const base = process.env.URBANTWIN_GRAFANA_URL?.trim();
  return base ? base.replace(/\/+$/, "") : null;
}

export function isMockMode(): boolean {
  return upstreamBase() === null;
}

export async function proxy(
  requestPath: string,
  init?: RequestInit,
  /** The AI advisor can take minutes when its hosted agent is waking from sleep. */
  timeoutMs = 30_000,
): Promise<Response> {
  const base = upstreamBase();
  if (!base) throw new Error("proxy() called with no URBANTWIN_API_BASE");

  try {
    const upstream = await fetch(`${base}${requestPath}`, {
      ...init,
      cache: "no-store",
      headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
      signal: AbortSignal.timeout(timeoutMs),
    });
    const body = await upstream.text();
    return new Response(body, {
      status: upstream.status,
      headers: { "content-type": "application/json" },
    });
  } catch (error) {
    return Response.json(
      {
        error: {
          code: "upstream_unavailable",
          message: `Configured backend at ${base} did not respond: ${
            error instanceof Error ? error.message : "unknown error"
          }`,
        },
      },
      { status: 502 },
    );
  }
}

export function json(body: unknown, status = 200): Response {
  return Response.json(body, {
    status,
    headers: { "cache-control": "no-store" },
  });
}
