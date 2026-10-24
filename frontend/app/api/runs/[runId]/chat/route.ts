import { isMockMode, json, proxy } from "@/lib/server/upstream";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ runId: string }> };

/** Live-only: recorded fixtures never pose as a conversation with the AI advisor. */
export async function POST(request: Request, ctx: Ctx) {
  const { runId } = await ctx.params;
  if (!isMockMode()) {
    return proxy(
      `/api/runs/${encodeURIComponent(runId)}/chat`,
      { method: "POST", body: await request.text() },
      180_000,
    );
  }
  return json(
    {
      error: {
        code: "not_found",
        message: "The advisor chat is available only with the live Python API.",
      },
    },
    404,
  );
}
