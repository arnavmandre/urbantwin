"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { HazardToolbar } from "@/components/HazardToolbar";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Icon } from "@/components/ui/Icon";
import { Dot, Pill } from "@/components/ui/Pill";
import { cx } from "@/lib/cx";
import { VIDEO_ELEMENT_ID } from "@/lib/viewer/kit-webrtc-adapter";
import {
  IDLE_VIEWER_STATE,
  selectViewerAdapter,
  type ViewerConnection,
  type ViewerState,
} from "@/lib/viewer";
import {
  VIEW_CAMERAS,
  type RunState,
  type StreamConfig,
  type ViewCamera,
  type ViewCommandResult,
  type ViewOverlay,
  type ViewPlayback,
} from "@/lib/types";

/**
 * The Omniverse viewport.
 *
 * This component renders viewer *state*; it contains no transport code. The
 * adapter in `lib/viewer/` owns connecting, and is chosen from what
 * `/api/stream/config` reports. Replacing the placeholder adapter with the
 * NVIDIA Kit App Streaming client therefore changes nothing here or anywhere
 * else in the dashboard.
 *
 * Mounted client-only: WebRTC and media APIs do not exist during SSR.
 *
 * It fills whatever box its parent gives it and floats its controls over the
 * picture. The parent must keep it mounted at a stable position: remounting
 * tears down the WebRTC session.
 */
export function OmniverseViewer({
  runId,
  config,
  state,
  onStateChange,
  hasAfter,
  onStatusChange,
  topRight,
  bottomInset = 0,
  className,
}: {
  runId: string | null;
  config: StreamConfig;
  state: RunState;
  onStateChange: (state: RunState) => void;
  hasAfter: boolean;
  /** Reports the real connection state, so chrome elsewhere never guesses. */
  onStatusChange?: (status: ViewerState["status"]) => void;
  /** Rendered at the end of the top-right control cluster. */
  topRight?: ReactNode;
  /** Height in px of chrome covering the bottom edge (the results peek). */
  bottomInset?: number;
  className?: string;
}) {
  const adapter = useMemo(() => selectViewerAdapter(config), [config]);
  const [viewer, setViewer] = useState<ViewerState>(IDLE_VIEWER_STATE);
  const [attempt, setAttempt] = useState(0);
  const [camera, setCamera] = useState<ViewCamera>("Overview");
  const [overlay, setOverlay] = useState<ViewOverlay>("behavior");
  const [playback, setPlayback] = useState<ViewPlayback>("play");
  const [commandResult, setCommandResult] = useState<ViewCommandResult | null>(null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const connectionRef = useRef<ViewerConnection | null>(null);
  const cleanupPromiseRef = useRef<Promise<void>>(Promise.resolve());
  const automaticRetriesRef = useRef(0);
  const runIdRef = useRef<string | null>(runId);
  const commandedRunIdRef = useRef<string | null>(runId);
  const commandedStateRef = useRef<RunState>(state);

  useEffect(() => {
    runIdRef.current = runId;
  }, [runId]);

  useEffect(() => {
    onStatusChange?.(viewer.status);
  }, [onStatusChange, viewer.status]);

  // Do NOT depend on runId: a finished simulation must not tear down WebRTC.
  useEffect(() => {
    const controller = new AbortController();
    let closed = false;

    const previousCleanup = cleanupPromiseRef.current;
    const connectionPromise = previousCleanup.then(() => adapter.connect({
        config,
        // Stable id for allow-list before the first simulation completes.
        runId: runIdRef.current ?? "viewport",
        signal: controller.signal,
        onState: (next) => {
          if (!closed) setViewer(next);
        },
        getRunId: () => runIdRef.current ?? "viewport",
      }));

    connectionPromise
      .then((connection) => {
        if (closed) {
          void connection.close();
          return;
        }
        connectionRef.current = connection;
      })
      .catch((error: unknown) => {
        if (closed || controller.signal.aborted) return;
        setViewer({
          status: "failed",
          message:
            error instanceof Error
              ? `The viewport adapter failed: ${error.message}`
              : "The viewport adapter failed for an unknown reason.",
          stream: null,
          capabilities: { video: false, input: false, messaging: false },
          detail: [],
        });
      });

    return () => {
      closed = true;
      controller.abort();
      connectionRef.current = null;
      cleanupPromiseRef.current = connectionPromise
        .then((connection) => connection.close())
        .catch(() => undefined);
    };
  }, [adapter, config, attempt]);

  useEffect(() => {
    if (viewer.status === "connected") {
      automaticRetriesRef.current = 0;
      return;
    }
    if (viewer.status !== "failed" || config.status !== "available") return;
    if (automaticRetriesRef.current >= 3) return;

    automaticRetriesRef.current += 1;
    const timer = window.setTimeout(() => setAttempt((value) => value + 1), 1500);
    return () => window.clearTimeout(timer);
  }, [config.status, viewer.status]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    // The streaming client owns srcObject on this element now, so only ever
    // set it — never clear it back to null, or we would tear down the live
    // stream the library just attached.
    if (viewer.stream && video.srcObject !== viewer.stream) {
      video.srcObject = viewer.stream;
    }
  }, [viewer.stream]);

  const sendCommand = useCallback(
    async (next: {
      state: RunState;
      camera: ViewCamera;
      overlay: ViewOverlay;
      playback: ViewPlayback;
    }) => {
      try {
        const result = await connectionRef.current?.send(next);
        if (result) {
          setCommandResult(result);
        } else {
          setCommandResult({
            accepted: false,
            delivered: false,
            reason:
              "No WebRTC viewport connection is available yet. Wait until the stream shows Live, then retry.",
            command: next,
          });
        }
      } catch {
        setCommandResult({
          accepted: false,
          delivered: false,
          reason: "The view command could not be sent.",
          command: next,
        });
      }
    },
    [],
  );

  const connected = viewer.status === "connected" && viewer.stream !== null;

  const commandProblem = !commandResult
    ? null
    : !commandResult.accepted
      ? (commandResult.reason ?? "The server rejected the command.")
      : !commandResult.delivered
        ? (commandResult.reason ?? "It could not be sent to Kit.")
        : !connected
          ? "The stream is not live, so Kit did not receive it."
          : null;

  // Problems clear themselves; the next command replaces them anyway.
  useEffect(() => {
    if (!commandProblem) return;
    const timer = window.setTimeout(() => setCommandResult(null), 6000);
    return () => window.clearTimeout(timer);
  }, [commandProblem]);

  useEffect(() => {
    if (!connected || !runId || commandedRunIdRef.current === runId) return;
    commandedRunIdRef.current = runId;
    setPlayback("play");
    commandedStateRef.current = state;
    void sendCommand({ state, camera, overlay, playback: "restart" });
  }, [camera, connected, overlay, runId, sendCommand, state]);

  // Before/After is owned by the dashboard and can change from the results
  // panel as well as from here; whichever control moved it, Kit follows.
  useEffect(() => {
    if (commandedStateRef.current === state) return;
    commandedStateRef.current = state;
    void sendCommand({ state, camera, overlay, playback });
  }, [camera, overlay, playback, sendCommand, state]);

  return (
    <div
      className={cx(
        "relative size-full overflow-hidden bg-canvas-tint",
        className,
      )}
    >
      <Backdrop />
      {/*
        Always mounted, and carrying the id the Kit streaming client binds to.
        AppStreamer attaches its mouse / wheel / keyboard forwarding to this
        exact element, so it must (a) exist before connect() runs and (b) be
        the element the user actually clicks. Drag to orbit, scroll to zoom.

        object-contain, never object-cover: the 1280x720 stream is letterboxed
        into whatever shape the workspace has instead of being cropped (cover
        used to cut off the top of the frame).

        The wrapper must hold nothing but the video. On connect, AppStreamer
        appends a `display: contents` div to the video's parent and moves the
        video into it; in a shared parent that put the video after the floating
        controls in DOM order, so the live picture painted over all of them.
      */}
      <div className="absolute inset-0 z-0">
        <video
          id={VIDEO_ELEMENT_ID}
          ref={videoRef}
          autoPlay
          playsInline
          muted
          tabIndex={0}
          aria-label="Omniverse RTX viewport. Drag to orbit, scroll to zoom."
          className={cx(
            "absolute inset-0 size-full object-contain outline-none",
            connected
              ? "cursor-grab active:cursor-grabbing"
              : "pointer-events-none opacity-0",
          )}
        />
      </div>
      {!connected && (
        <div
          className="absolute inset-x-0 top-0 z-10 grid place-items-center p-6 pt-24"
          style={{ bottom: bottomInset }}
        >
          <ViewerStatePanel
            viewer={viewer}
            adapterName={adapter.displayName}
            onRetry={() => {
              automaticRetriesRef.current = 0;
              setAttempt((n) => n + 1);
            }}
          />
        </div>
      )}

      {/* Floating chrome. The layer itself ignores the pointer so the stream
          stays draggable between controls; each control opts back in. */}
      <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex flex-wrap items-start justify-between gap-2 p-3 sm:p-4">
        <HazardToolbar
          overlay={overlay}
          onOverlayChange={(next) => {
            setOverlay(next);
            void sendCommand({ state, camera, overlay: next, playback });
          }}
        />

        <div className="pointer-events-auto ml-auto flex flex-wrap items-center justify-end gap-2">
          <div className="flex items-center gap-2 rounded-[12px] border border-hairline bg-surface/95 p-1 pl-2 shadow-[var(--shadow-card)]">
            <StatusChip status={viewer.status} />
            <SegmentedControl
              ariaLabel="Simulation state shown in the viewport"
              size="sm"
              value={state}
              onChange={onStateChange}
              segments={[
                { value: "before", label: "Before" },
                {
                  value: "after",
                  label: "After",
                  disabled: !hasAfter,
                  title: hasAfter
                    ? undefined
                    : "This run has no intervention arm to show.",
                },
              ]}
            />
            <label className="flex items-center gap-1.5 pr-1 text-[12px] text-ink-2">
              <span className="sr-only sm:not-sr-only text-ink-3">Camera</span>
              <select
                value={camera}
                onChange={(event) => {
                  const next = event.target.value as ViewCamera;
                  setCamera(next);
                  void sendCommand({ state, camera: next, overlay, playback });
                }}
                className="rounded-[8px] border border-hairline bg-surface-2 px-2 py-1 text-[12px] text-ink"
              >
                {VIEW_CAMERAS.map((option) => (
                  <option key={option} value={option}>
                    {CAMERA_LABEL[option]}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {topRight}
          {/* On Pune, Kit's demoState "Intervention" variant holds this run's
              after-arm walkers, heat map and the applied interventions at illustrative
              positions (cities/pune/pune_view.py). Said whenever the 3D "After" is on screen. */}
          {connected && state === "after" ? (
            <p className="basis-full text-right">
              <span className="inline-block rounded-[8px] bg-surface/90 px-2 py-0.5 text-[11px] text-ink-3 shadow-[var(--shadow-card)] backdrop-blur">
                3D &ldquo;After&rdquo; shows this run&rsquo;s re-simulated citizens; added shade, drains or footpaths are drawn at illustrative positions.
              </span>
            </p>
          ) : null}
        </div>
      </div>

      <div
        className="pointer-events-none absolute inset-x-0 z-10 flex flex-wrap items-end gap-2 px-3 pb-3 sm:px-4"
        style={{ bottom: bottomInset }}
      >
        <div
          className="pointer-events-auto flex items-center gap-1 rounded-[12px] border border-hairline bg-surface/95 p-1 shadow-[var(--shadow-card)]"
          role="group"
          aria-label="Animation playback"
        >
          <span className="px-1.5 text-[11px] text-ink-3">Animation</span>
          {(["play", "pause", "restart"] as const).map((action) => (
            <button
              key={action}
              type="button"
              disabled={!connected}
              aria-label={`${action[0].toUpperCase()}${action.slice(1)} animation`}
              aria-pressed={action === "restart" ? undefined : playback === action}
              onClick={() => {
                setPlayback(action === "pause" ? "pause" : "play");
                void sendCommand({
                  state,
                  camera,
                  overlay,
                  playback: action,
                });
              }}
              className={cx(
                "grid size-7 place-items-center rounded-[8px] border transition-colors disabled:cursor-not-allowed disabled:opacity-40",
                (action === "pause" ? playback === "pause" : action === "play" ? playback === "play" : false)
                  ? "border-accent-line bg-accent-soft text-accent"
                  : "border-transparent text-ink-2 hover:bg-surface-2",
              )}
            >
              <Icon name={action} className="size-3.5" />
            </button>
          ))}
          <span className="hidden px-1.5 text-[11px] text-ink-3 lg:inline">
            {adapter.transportLabel}
          </span>
        </div>

        {/* Only problems are reported. A command that was sent stays silent:
            `delivered` only means the browser's send resolved, so there is no
            confirmation worth showing, and the viewport itself shows the change. */}
        {commandProblem ? (
          <p
            role="status"
            className="pointer-events-auto max-w-[min(480px,100%)] rounded-[10px] border border-[color:var(--negative)]/25 bg-surface/95 px-3 py-1.5 text-[11.5px] leading-relaxed text-ink-2 shadow-[var(--shadow-card)] backdrop-blur"
          >
            <span className="font-semibold text-negative">View change not applied.</span>{" "}
            {commandProblem}
          </p>
        ) : null}
      </div>
    </div>
  );
}

function StatusChip({ status }: { status: ViewerState["status"] }) {
  const map = {
    idle: { tone: "neutral", label: "Idle", color: "var(--ink-4)" },
    connecting: { tone: "caution", label: "Connecting", color: "var(--caution)" },
    connected: { tone: "positive", label: "Live", color: "var(--positive)" },
    offline: { tone: "neutral", label: "Offline", color: "var(--ink-4)" },
    failed: { tone: "negative", label: "Failed", color: "var(--negative)" },
  } as const;
  const entry = map[status];
  return (
    <Pill tone={entry.tone}>
      <Dot color={entry.color} className={status === "connecting" ? "breathe" : undefined} />
      {entry.label}
    </Pill>
  );
}

function ViewerStatePanel({
  viewer,
  adapterName,
  onRetry,
}: {
  viewer: ViewerState;
  adapterName: string;
  onRetry: () => void;
}) {
  if (viewer.status === "connecting" || viewer.status === "idle") {
    return (
      <div className="flex flex-col items-center gap-3 text-center">
        <Spinner />
        <p className="text-[13px] text-ink-2">
          {viewer.message || "Preparing the viewport\u2026"}
        </p>
      </div>
    );
  }

  const failed = viewer.status === "failed";

  return (
    <div className="max-w-md rounded-[16px] border border-hairline bg-surface/85 p-5 text-center shadow-[var(--shadow-lift)] backdrop-blur-xl">
      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-3">
        {failed ? "Viewport failed" : "Viewport offline"}
      </p>
      <p className="mt-2 text-[15px] font-semibold tracking-[-0.015em] text-ink">
        No live RTX stream is connected
      </p>
      {failed ? (
        <>
          <p className="mt-2 text-[13px] leading-relaxed text-ink-2">
            The stream did not start. Retry; if it fails again, restart Kit. The
            results do not depend on the stream.
          </p>
          <details className="mt-3 text-left">
            <summary className="cursor-pointer text-[12px] font-semibold text-ink-2">
              Technical details
            </summary>
            <ViewerMessage viewer={viewer} />
          </details>
        </>
      ) : (
        <ViewerMessage viewer={viewer} />
      )}
      <div className="mt-4 flex items-center justify-center gap-2">
        <button
          type="button"
          onClick={onRetry}
          className="rounded-full bg-accent px-4 py-1.5 text-[12px] font-semibold text-accent-ink transition-colors hover:bg-accent-hover"
        >
          Retry connection
        </button>
        <span className="text-[11px] text-ink-3">via {adapterName}</span>
      </div>
    </div>
  );
}

const CAMERA_LABEL: Record<ViewCamera, string> = {
  Overview: "Overview",
  Street: "Street",
  ProblemZone: "Problem zone",
  Aerial: "Aerial",
};

function ViewerMessage({ viewer }: { viewer: ViewerState }) {
  return (
    <>
      <p className="mt-2 text-[13px] leading-relaxed text-ink-2">{viewer.message}</p>
      {viewer.detail.length > 0 ? (
        <ul className="mt-3 space-y-1 text-left">
          {viewer.detail.map((line) => (
            <li key={line} className="text-[12px] leading-relaxed text-ink-3">
              {line}
            </li>
          ))}
        </ul>
      ) : null}
    </>
  );
}

function Spinner() {
  return (
    <span
      aria-hidden
      className="size-6 animate-spin rounded-full border-2 border-hairline-strong border-t-accent"
    />
  );
}

/**
 * An abstract backdrop for the empty viewport. Deliberately a plain grid, not a
 * drawing of a city: nothing here should be mistaken for the rendered twin.
 */
function Backdrop() {
  return (
    <div
      aria-hidden
      className="absolute inset-0 bg-canvas-tint"
      style={{
        backgroundImage:
          "linear-gradient(var(--hairline) 1px, transparent 1px), linear-gradient(90deg, var(--hairline) 1px, transparent 1px)",
        backgroundSize: "44px 44px",
        maskImage: "radial-gradient(ellipse at center, black 35%, transparent 85%)",
        WebkitMaskImage: "radial-gradient(ellipse at center, black 35%, transparent 85%)",
      }}
    />
  );
}
