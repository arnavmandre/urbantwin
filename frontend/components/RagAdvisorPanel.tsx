"use client";

import { useCallback, useState } from "react";

import { Card, CardHeader } from "@/components/ui/Card";
import { Pill } from "@/components/ui/Pill";
import { api } from "@/lib/api";
import type { RagAdvisorResponse, RecommendationId } from "@/lib/types";

export const ACTION_LABELS: Record<string, string> = {
  increase_shade: "Increase shade",
  improve_drainage: "Improve drainage",
  alternative_pedestrian_routes: "Open alternative pedestrian routes",
  no_major_intervention: "No major intervention",
};

/** On-demand to avoid spending advisor-model credits until the operator asks for advice. */
export function RagAdvisorPanel({
  runId,
  busy,
  onApplySelected,
}: {
  runId: string;
  busy: boolean;
  onApplySelected: (ids: RecommendationId[]) => void;
}) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<RagAdvisorResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Record<string, boolean>>({});

  const retrieve = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.advise(runId);
      setResult(response);
      setSelected(
        Object.fromEntries(
          response.recommendations.map((recommendation) => [
            `${recommendation.rank}:${recommendation.argus_recommendation_id}`,
            recommendation.argus_recommendation_id !== "no_major_intervention",
          ]),
        ),
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Grounded advice failed.");
    } finally {
      setLoading(false);
    }
  }, [runId]);

  return (
    <Card>
      <CardHeader
        eyebrow="AI decision support"
        title="Urban advisor"
        description="The AI advisor uses retrieved planning evidence to explain the risks and propose actions. Select one or several actions to test in a new simulation."
        actions={result ? (
          <Pill tone={result.fallback_used ? "caution" : "accent"}>
            {result.fallback_used ? "Deterministic fallback" : "RAG grounded"}
          </Pill>
        ) : null}
      />

      {!result ? (
        <button
          type="button"
          onClick={() => void retrieve()}
          disabled={loading}
          className="mt-4 w-full rounded-[12px] border border-hairline bg-surface-2 px-4 py-2.5 text-[13px] font-semibold text-ink transition-colors hover:bg-surface-3 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Retrieving advice…" : "Retrieve grounded advice"}
        </button>
      ) : (
        <div className="mt-4 space-y-3">
          {result.recommendations.map((recommendation) => {
            const selectionKey = `${recommendation.rank}:${recommendation.argus_recommendation_id}`;
            return (
            <div key={selectionKey} className="rounded-[14px] border border-hairline bg-surface-2 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <label className="flex cursor-pointer items-center gap-2 text-[14px] font-semibold text-ink">
                  <input
                    type="checkbox"
                    checked={Boolean(selected[selectionKey])}
                    disabled={busy}
                    onChange={(event) =>
                      setSelected((current) => ({
                        ...current,
                        [selectionKey]: event.target.checked,
                      }))
                    }
                    className="size-4 accent-[var(--accent)]"
                  />
                  <span>{recommendation.rank}. {recommendation.intervention ?? ACTION_LABELS[recommendation.argus_recommendation_id]}</span>
                </label>
                {recommendation.knowledge_id ? <Pill tone="neutral">{recommendation.knowledge_id}</Pill> : null}
              </div>
              {recommendation.reason ? <p className="mt-2 text-[12.5px] leading-relaxed text-ink-2">{recommendation.reason}</p> : null}
              {recommendation.tradeoffs?.length ? (
                <p className="mt-2 text-[11px] leading-relaxed text-ink-3">Trade-offs: {recommendation.tradeoffs.join("; ")}</p>
              ) : null}
              {recommendation.source?.status === "VERIFIED" && recommendation.source.url ? (
                <a className="mt-2 inline-block text-[11px] font-semibold text-accent hover:underline" href={recommendation.source.url} target="_blank" rel="noreferrer">
                  {recommendation.source.title}
                </a>
              ) : recommendation.source ? (
                <p className="mt-2 text-[11px] text-caution">Source pending verification</p>
              ) : null}
            </div>
          )})}
          <p className="text-[11px] leading-relaxed text-ink-3">
            {result.fallback_used
              ? `No LLM output was used: ${result.unavailable_reason ?? "the deterministic fallback answered."}`
              : `Confirmed LLM output from ${result.model ?? "the configured advisor model"}. Retrieval: ${result.retrieval_backend ?? "unknown"}.`}
          </p>
          <button
            type="button"
            disabled={
              busy ||
              !result.recommendations.some(
                (recommendation) =>
                  selected[`${recommendation.rank}:${recommendation.argus_recommendation_id}`],
              )
            }
            onClick={() =>
              onApplySelected(
                result.recommendations
                  .filter(
                    (recommendation) =>
                      selected[`${recommendation.rank}:${recommendation.argus_recommendation_id}`],
                  )
                  .map((recommendation) => recommendation.argus_recommendation_id),
              )
            }
            className="w-full rounded-[12px] bg-accent px-4 py-2.5 text-[13px] font-semibold text-accent-ink transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:bg-surface-3 disabled:text-ink-3"
          >
            Test selected actions together
          </button>
          <p className="text-[11px] leading-relaxed text-ink-3">
            Select one action to isolate its effect, or select several actions to measure their combined effect.
          </p>
        </div>
      )}
      {error ? <p className="mt-3 text-[11px] text-negative">{error}</p> : null}
    </Card>
  );
}
