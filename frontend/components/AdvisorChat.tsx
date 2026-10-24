"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Card, CardHeader } from "@/components/ui/Card";
import { Pill } from "@/components/ui/Pill";
import { api } from "@/lib/api";
import { cx } from "@/lib/cx";
import type { AdvisorChatResponse, RecommendationId } from "@/lib/types";

type Message =
  | { role: "planner"; text: string }
  | { role: "advisor"; response: AdvisorChatResponse }
  | { role: "note"; text: string };

const ACTION_LABELS: Record<RecommendationId, string> = {
  increase_shade: "Increase shade",
  improve_drainage: "Improve drainage",
  alternative_pedestrian_routes: "Open alternative pedestrian routes",
  no_major_intervention: "No major intervention",
};

const STARTERS = [
  "What is the biggest problem in this run?",
  "Why is the top problem zone flagged?",
  "What should we test next, and why?",
];

/**
 * Conversation with the AI advisor (Agent 37) about the run on screen. The conversation survives
 * re-runs: when a new run completes, the backend gives the advisor that run's facts so it can compare.
 * Proposals are validated server-side against the actions the simulator can execute.
 */
export function AdvisorChat({
  runId,
  busy,
  attemptStatus,
  onApply,
}: {
  runId: string;
  busy: boolean;
  /** Status of the latest run attempt, so a failed or cancelled re-run clears its pending comparison. */
  attemptStatus: string;
  onApply: (ids: RecommendationId[]) => void;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [seenRun, setSeenRun] = useState(runId);
  // Actions applied from this chat whose re-run has not reported back yet.
  const [pendingApply, setPendingApply] = useState<RecommendationId[] | null>(null);
  const [autoCompare, setAutoCompare] = useState<string | null>(null);
  const scroller = useRef<HTMLDivElement>(null);

  // A new run arrived: mark it in the thread (the backend injects its facts). If it is the re-run of
  // an action applied here, ask the advisor straight away what changed.
  if (seenRun !== runId) {
    setSeenRun(runId);
    if (pendingApply) {
      const applied = pendingApply.map((id) => ACTION_LABELS[id]).join(" + ");
      setPendingApply(null);
      setMessages((prev) => [...prev, { role: "note", text: `Re-run ${runId} with ${applied} finished.` }]);
      setAutoCompare(
        `I applied ${applied} and the re-run finished. What improved and what got worse, compared with the ` +
          "previous run and with this run's own baseline (before arm)? Use the numbers, and say whether you " +
          "would keep it.",
      );
    } else if (messages.length > 0) {
      setMessages((prev) => [
        ...prev,
        { role: "note", text: `New run ${runId} finished. Ask the advisor how it compares.` },
      ]);
    }
  }

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  const send = useCallback(
    async (text: string) => {
      const message = text.trim();
      if (!message || sending) return;
      setAutoCompare(null); // a queued automatic comparison is being sent now (or superseded by the planner)
      setInput("");
      setError(null);
      setMessages((prev) => [...prev, { role: "planner", text: message }]);
      setSending(true);
      try {
        const response = await api.chat(runId, message, sessionId);
        setSessionId(response.session_id);
        setMessages((prev) => [...prev, { role: "advisor", response }]);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "The advisor did not answer.");
      } finally {
        setSending(false);
      }
    },
    [runId, sending, sessionId],
  );

  // A re-run started from here that failed or was cancelled must not leave a pending comparison
  // behind for some later, unrelated run.
  const [seenStatus, setSeenStatus] = useState(attemptStatus);
  if (seenStatus !== attemptStatus) {
    setSeenStatus(attemptStatus);
    if (pendingApply && (attemptStatus === "failed" || attemptStatus === "cancelled")) {
      setPendingApply(null);
      setMessages((prev) => [
        ...prev,
        { role: "note", text: `The re-run ${attemptStatus === "failed" ? "failed" : "was cancelled"}, so there is nothing new to compare.` },
      ]);
    }
  }

  useEffect(() => {
    // Sending the comparison request is the external sync this effect exists for; the state updates
    // inside send() are that request's own lifecycle (thinking indicator, reply), not derived state.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (autoCompare && !sending) void send(autoCompare);
  }, [autoCompare, send, sending]);

  const apply = useCallback(
    (ids: RecommendationId[]) => {
      setPendingApply(ids);
      onApply(ids);
    },
    [onApply],
  );

  return (
    <Card>
      <CardHeader
        eyebrow="AI decision support"
        title="Chat with the advisor"
        description="Ask why a place is flagged, challenge a recommendation or suggest your own idea. The advisor answers from this run's simulator numbers, and anything it proposes can be tested with a re-run."
        actions={<Pill tone="accent">Agent 37</Pill>}
      />

      <div
        ref={scroller}
        aria-live="polite"
        className="mt-4 max-h-[420px] space-y-3 overflow-y-auto rounded-[12px] border border-hairline bg-surface-2 p-3"
      >
        {messages.length === 0 ? (
          <div className="flex flex-wrap gap-2">
            {STARTERS.map((starter) => (
              <button
                key={starter}
                type="button"
                disabled={sending}
                onClick={() => void send(starter)}
                className="rounded-full border border-hairline bg-surface px-3 py-1.5 text-[12px] text-ink-2 transition-colors hover:text-ink disabled:opacity-50"
              >
                {starter}
              </button>
            ))}
          </div>
        ) : null}

        {messages.map((message, index) =>
          message.role === "note" ? (
            <p key={index} className="text-center text-[11px] text-ink-3">
              {message.text}
            </p>
          ) : message.role === "planner" ? (
            <div key={index} className="flex justify-end">
              <p className="max-w-[85%] whitespace-pre-wrap rounded-[12px] bg-accent px-3 py-2 text-[13px] text-accent-ink">
                {message.text}
              </p>
            </div>
          ) : (
            <AdvisorTurn key={index} response={message.response} busy={busy} onApply={apply} />
          ),
        )}

        {sending ? (
          <p className="text-[12px] text-ink-3">
            <span className="breathe mr-2 inline-block size-2 rounded-full bg-accent align-middle" />
            The advisor is thinking. The first reply can take longer if the agent is waking up.
          </p>
        ) : null}
      </div>

      {error ? (
        <p role="alert" className="mt-2 text-[12px] text-negative">
          {error}
        </p>
      ) : null}

      <form
        className="mt-3 flex items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void send(input);
        }}
      >
        <textarea
          value={input}
          rows={2}
          maxLength={2000}
          placeholder="Ask, challenge or suggest..."
          aria-label="Message to the advisor"
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void send(input);
            }
          }}
          className="min-h-[44px] flex-1 resize-y rounded-[12px] border border-hairline bg-surface px-3 py-2 text-[13px] text-ink outline-none focus:border-accent-line"
        />
        <button
          type="submit"
          disabled={sending || !input.trim()}
          className="rounded-[12px] bg-accent px-4 py-2.5 text-[13px] font-semibold text-accent-ink transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
        >
          Send
        </button>
      </form>
      <p className="mt-2 text-[11px] leading-relaxed text-ink-3">
        The advisor explains and proposes; the simulator stays the only source of metrics. It can test four
        actions: more shade, better drainage, alternative pedestrian routes, or no major change.
      </p>
    </Card>
  );
}

function AdvisorTurn({
  response,
  busy,
  onApply,
}: {
  response: AdvisorChatResponse;
  busy: boolean;
  onApply: (ids: RecommendationId[]) => void;
}) {
  const fallback = response.source !== "agent37";
  return (
    <div className="max-w-[92%] space-y-2">
      <div
        className={cx(
          "rounded-[12px] border px-3 py-2 text-[13px] leading-relaxed text-ink",
          fallback ? "border-[color:var(--caution)]/40 bg-surface" : "border-hairline bg-surface",
        )}
      >
        <p className="whitespace-pre-wrap">{response.reply}</p>
        {fallback && response.unavailable_reason ? (
          <p className="mt-1 text-[11px] text-ink-3">Advisor unavailable: {response.unavailable_reason}</p>
        ) : null}
      </div>
      {response.proposals.map((proposal) => (
        <div
          key={proposal.action}
          className="flex items-center gap-3 rounded-[12px] border border-accent-line bg-accent-soft px-3 py-2"
        >
          <div className="min-w-0 flex-1">
            <p className="text-[12px] font-semibold text-accent">
              {ACTION_LABELS[proposal.action] ?? proposal.action}
            </p>
            {proposal.reason ? <p className="text-[11px] text-ink-2">{proposal.reason}</p> : null}
          </div>
          <button
            type="button"
            disabled={busy}
            onClick={() => onApply([proposal.action])}
            className="shrink-0 rounded-[10px] bg-accent px-3 py-1.5 text-[12px] font-semibold text-accent-ink transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            Apply &amp; re-run
          </button>
        </div>
      ))}
    </div>
  );
}
