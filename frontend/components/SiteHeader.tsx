"use client";

import { useSyncExternalStore, type ReactNode } from "react";

import { Icon } from "@/components/ui/Icon";
import { Dot, Pill, type PillTone } from "@/components/ui/Pill";
import type { Health } from "@/lib/types";
import type { ViewerState } from "@/lib/viewer";

const VIEWPORT_STATUS: Record<
  ViewerState["status"],
  { tone: PillTone; label: string; color: string }
> = {
  idle: { tone: "neutral", label: "Viewport idle", color: "var(--ink-4)" },
  connecting: { tone: "caution", label: "Viewport connecting", color: "var(--caution)" },
  connected: { tone: "positive", label: "Viewport live", color: "var(--positive)" },
  offline: { tone: "neutral", label: "Viewport offline", color: "var(--ink-4)" },
  failed: { tone: "negative", label: "Viewport failed", color: "var(--negative)" },
};

/**
 * Compact top bar. It carries the two claims that matter most: whether the
 * backend is live (read only from `/api/health`) and whether the 3D stream is
 * actually connected (read from the WebRTC adapter's own state, not from the
 * TCP probe, which reports a stale listener as "online").
 */
export function SiteHeader({
  health,
  viewerStatus,
  sceneLabel,
  aboutOpen: open,
  onAboutOpenChange,
  about,
}: {
  health: Health;
  viewerStatus: ViewerState["status"];
  sceneLabel: string;
  /** The About & status panel is owned by the page so results can open it. */
  aboutOpen: boolean;
  onAboutOpenChange: (open: boolean) => void;
  /** Prototype methodology and limitations, shown at the top of the panel. */
  about: ReactNode;
}) {
  const fullscreen = useFullscreen();

  const live = health.mode === "live" && health.capabilities.live_simulation;
  const tone = live ? "positive" : health.status === "offline" ? "negative" : "caution";
  const label =
    health.status === "offline"
      ? "Backend unreachable"
      : live
        ? "Live backend"
        : "Recorded data";
  const viewport = VIEWPORT_STATUS[viewerStatus];

  return (
    <header className="relative z-40 shrink-0 border-b border-hairline bg-surface">
      <div className="flex items-center gap-x-3 px-3 py-2 sm:px-5">
        <div className="flex min-w-0 items-center gap-2.5">
          <Mark />
          <div className="min-w-0 leading-tight">
            <p className="truncate text-[14px] font-semibold tracking-[-0.02em] text-ink">
              Argus AI
            </p>
            <p className="hidden truncate text-[11px] text-ink-3 lg:block">
              Simulate the human experience before building the city
            </p>
          </div>
        </div>

        <span
          className="hidden min-w-0 truncate rounded-[8px] border border-hairline px-2 py-1 text-[11.5px] text-ink-2 md:inline"
          title="Scene shown in the viewport"
        >
          {sceneLabel}
        </span>

        <div className="ml-auto flex items-center gap-1.5 sm:gap-2">
          <Pill tone={tone} title={label}>
            <Dot
              color={
                live
                  ? "var(--positive)"
                  : health.status === "offline"
                    ? "var(--negative)"
                    : "var(--caution)"
              }
            />
            <span className="hidden sm:inline">{label}</span>
            <span className="sr-only sm:hidden">{label}</span>
          </Pill>
          <Pill tone={viewport.tone} title={viewport.label}>
            <Dot
              color={viewport.color}
              className={viewerStatus === "connecting" ? "breathe" : undefined}
            />
            <span className="hidden sm:inline">{viewport.label}</span>
            <span className="sr-only sm:hidden">{viewport.label}</span>
          </Pill>
          <button
            type="button"
            onClick={() => onAboutOpenChange(!open)}
            aria-expanded={open}
            aria-controls="status-panel"
            className="flex items-center gap-1.5 rounded-full border border-hairline px-2.5 py-1 text-[11px] font-semibold text-ink-2 transition-colors hover:text-ink"
          >
            <Icon name="info" className="size-3.5" />
            <span className="hidden sm:inline">About &amp; status</span>
            <span className="sr-only sm:hidden">About and status</span>
          </button>
          {fullscreen.supported ? (
            <button
              type="button"
              onClick={fullscreen.toggle}
              aria-pressed={fullscreen.active}
              aria-label={fullscreen.active ? "Exit fullscreen" : "Enter fullscreen"}
              title={fullscreen.active ? "Exit fullscreen" : "Fullscreen"}
              className="grid size-7 place-items-center rounded-full border border-hairline text-ink-2 transition-colors hover:text-ink"
            >
              <Icon name={fullscreen.active ? "collapse" : "expand"} className="size-3.5" />
            </button>
          ) : null}
        </div>
      </div>

      {open ? (
        <div
          id="status-panel"
          role="region"
          aria-label="About and status"
          className="absolute inset-x-0 top-full max-h-[min(78dvh,760px)] overflow-y-auto border-b border-hairline bg-surface shadow-[var(--shadow-lift)]"
        >
          <div className="mx-auto max-w-[1560px] space-y-5 px-5 py-4 sm:px-8">
            {about}
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-3">
              What is live
            </p>
            <div className="grid gap-x-8 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
              <div>
                <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-3">
                  Capabilities
                </p>
                <ul className="space-y-1.5">
                  {Object.entries(health.capabilities).map(([key, value]) => (
                    <li key={key} className="flex items-center gap-2 text-[12px] text-ink-2">
                      <Dot color={value ? "var(--positive)" : "var(--ink-4)"} />
                      <span>{capabilityLabel(key)}</span>
                      <span className="ml-auto tabular text-ink-3">
                        {value ? "available" : "not built"}
                      </span>
                    </li>
                  ))}
                </ul>
                <p className="mt-3 text-[12px] text-ink-2">
                  Kit signaling probe: {health.omniverse_stream}
                </p>
                <p className="mt-0.5 text-[11px] leading-relaxed text-ink-3">
                  The probe is only a TCP connect, so a stale listener reads as
                  online. The viewport status in the bar is the WebRTC
                  connection itself.
                </p>
              </div>
              <div className="sm:col-span-1 lg:col-span-2">
                <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-3">
                  Reported by /api/health
                </p>
                <ul className="space-y-1.5">
                  {health.notes.map((note) => (
                    <li key={note} className="text-[12px] leading-relaxed text-ink-2">
                      {note}
                    </li>
                  ))}
                </ul>
                <p className="mt-3 text-[11px] text-ink-3">
                  Checked {new Date(health.checked_utc).toLocaleString()}
                </p>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </header>
  );
}

/** Display names only; the keys are the `/api/health` capability ids. */
const CAPABILITY_LABELS: Record<string, string> = {
  http_api: "HTTP API",
  live_simulation: "Live Simulation",
  omniverse_streaming: "Omniverse Streaming",
  llm_advisor: "LLM Advisor",
  random_forest_inference: "Random Forest Inference",
  run_persistence: "Run Persistence",
};

function capabilityLabel(key: string): string {
  return (
    CAPABILITY_LABELS[key] ??
    key.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase())
  );
}

/** Standard Fullscreen API on the whole app, so the drawers stay usable. */
function subscribeFullscreen(onChange: () => void) {
  document.addEventListener("fullscreenchange", onChange);
  return () => document.removeEventListener("fullscreenchange", onChange);
}

function useFullscreen() {
  const supported = useSyncExternalStore(
    subscribeFullscreen,
    () => Boolean(document.fullscreenEnabled),
    () => false,
  );
  const active = useSyncExternalStore(
    subscribeFullscreen,
    () => document.fullscreenElement !== null,
    () => false,
  );

  const toggle = () => {
    if (document.fullscreenElement) {
      void document.exitFullscreen().catch(() => undefined);
    } else {
      void document.documentElement.requestFullscreen().catch(() => undefined);
    }
  };

  return { supported, active, toggle };
}

function Mark() {
  return (
    <span
      aria-hidden
      className="grid size-7 shrink-0 place-items-center rounded-[8px] bg-accent text-accent-ink"
    >
      <svg viewBox="0 0 24 24" className="size-[16px]" fill="none" strokeWidth="1.8">
        <path
          d="M4 20V9.5L12 4l8 5.5V20"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path d="M9.5 20v-5.5h5V20" stroke="currentColor" strokeLinecap="round" />
      </svg>
    </span>
  );
}
