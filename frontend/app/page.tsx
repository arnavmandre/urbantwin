import { Dashboard } from "@/components/Dashboard";
import { loadBootstrap } from "@/lib/server/bootstrap";

export const dynamic = "force-dynamic";

// Same shape the pipeline accepts (integration/run_pipeline.py RUN_ID_PATTERN).
const RUN_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;

export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const { run } = await searchParams;
  // ?run=<id> survives a reload; anything else falls back to the default run.
  const runId = typeof run === "string" && RUN_ID.test(run) ? run : undefined;
  const bootstrap = await loadBootstrap(runId);
  return <Dashboard bootstrap={bootstrap} />;
}
