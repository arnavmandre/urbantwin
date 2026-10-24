import { api } from "../api";
import type {
  ViewerAdapter,
  ViewerConnectContext,
  ViewerConnection,
  ViewerState,
} from "./adapter";
import type { AppStreamer } from "@nvidia/ov-web-rtc";
import type { StreamConfig, ViewCommand } from "../types";

export const VIDEO_ELEMENT_ID = "urbantwin-kit-stream";
const AUDIO_ELEMENT_ID = "urbantwin-kit-audio";

// 720p30. Must match renderer.resolution in urbantwin_streaming.kit, or Kit
// renders at one size and the encoder rescales, paying for both. 1080p60 kept
// a laptop RTX 5060 pinned at 100% / 78 C.
const STREAM_WIDTH = 1280;
const STREAM_HEIGHT = 720;
const STREAM_FPS = 30;
const MEDIA_STREAM_WAIT_MS = 15000;
/** Wait for a drag-resize to settle before asking Kit to re-render. */
const FIT_DEBOUNCE_MS = 300;
/** Local Kit signaling should answer well before this; fail instead of spinning forever. */
const CONNECT_TIMEOUT_MS = 45_000;

/**
 * NVIDIA Kit App Streaming adapter (`@nvidia/ov-web-rtc`).
 *
 * Connects with {@link StreamType.DIRECT}, renders into off-DOM media elements,
 * then hands the video element's `srcObject` MediaStream to the viewer surface.
 */
export const kitWebRtcViewerAdapter: ViewerAdapter = {
  id: "nvidia-kit-webrtc",
  displayName: "NVIDIA Kit App Streaming",
  transportLabel: "WebRTC \u00b7 Kit App Streaming",

  async connect(ctx: ViewerConnectContext): Promise<ViewerConnection> {
    const { config, onState, signal, runId, getRunId } = ctx;
    const resolveRunId = () => getRunId?.() ?? runId ?? "viewport";

    onState({
      status: "connecting",
      message: "Connecting to local Kit App Streaming\u2026",
      stream: null,
      capabilities: { video: false, input: false, messaging: false },
      detail: [],
    });

    if (config.status !== "available" || !config.signaling_url) {
      onState(offlineState(config));
      return inertConnection(
        "No signaling URL was returned by /api/stream/config.",
        resolveRunId,
      );
    }

    const endpoints = resolveDirectEndpoints(config);
    if (!endpoints) {
      onState({
        status: "offline",
        message:
          config.reason ??
          "A session was advertised but host and port details for Kit App Streaming are missing.",
        stream: null,
        capabilities: { video: false, input: false, messaging: false },
        detail: [
          `Stage: ${config.stage}`,
          "Expected signaling_host, signaling_port, media_host, and media_port from /api/stream/config.",
        ],
      });
      return inertConnection(
        "Stream config is missing signaling or media host/port fields.",
        resolveRunId,
      );
    }

    if (signal.aborted) {
      throw new DOMException("aborted", "AbortError");
    }

    const { AppStreamer, StreamType, EventStatus } = await import(
      "@nvidia/ov-web-rtc"
    );

    const mediaElements = createHiddenMediaElements();
    const streamer = new AppStreamer();
    let tornDown = false;
    let sawStartSuccess = false;
    let stopFitting: () => void = () => undefined;

    const teardown = async () => {
      if (tornDown) return;
      tornDown = true;
      stopFitting();
      try {
        await streamer.terminate();
      } catch {
        /* best-effort */
      }
      removeHiddenMediaElements(mediaElements);
    };

    const onAbort = () => {
      void teardown();
    };
    signal.addEventListener("abort", onAbort, { once: true });

    const iceServerConfiguration =
      config.ice_servers.length > 0
        ? {
            iceServers: config.ice_servers.map((entry) => ({
              urls: entry.urls,
              username: entry.username,
              credential: entry.credential,
            })),
          }
        : undefined;

    let connectFailed = false;

    // Local Kit (Phase 13) has no session manager. Do not pass our API nonce as
    // sessionId — NVIDIA's local sample omits it so the client talks straight to
    // the signaling port. A fabricated sessionId makes connect hang forever.
    const streamConfig = {
      signalingServer: endpoints.signalingHost,
      signalingPort: endpoints.signalingPort,
      mediaServer: endpoints.mediaHost,
      // Match NVIDIA local sample: omit mediaPort so the client discovers it.
      ...(endpoints.mediaPort != null ? { mediaPort: endpoints.mediaPort } : {}),
      videoElementId: VIDEO_ELEMENT_ID,
      audioElementId: AUDIO_ELEMENT_ID,
      authenticate: false as const,
      autoLaunch: true,
      width: STREAM_WIDTH,
      height: STREAM_HEIGHT,
      fps: STREAM_FPS,
      maxReconnects: 5,
      iceServerConfiguration,
      onStart: (message: { status: string; info?: string | Error }) => {
        if (signal.aborted || tornDown) return;

        if (message.status === EventStatus.IN_PROGRESS) {
          onState({
            status: "connecting",
            message: "Negotiating WebRTC with the RTX host\u2026",
            stream: null,
            capabilities: { video: false, input: false, messaging: false },
            detail: [
              `Signaling ${endpoints.signalingHost}:${endpoints.signalingPort}`,
              endpoints.mediaPort != null
                ? `Media ${endpoints.mediaHost}:${endpoints.mediaPort}`
                : `Media ${endpoints.mediaHost} (port auto)`,
            ],
          });
          return;
        }

        if (message.status === EventStatus.SUCCESS) {
          sawStartSuccess = true;
          if (!mediaElements.ownsVideo) {
            stopFitting();
            stopFitting = fitStreamToElement(streamer, mediaElements.video);
          }
          void publishStreamWhenReady(
            mediaElements.video,
            signal,
            config,
            onState,
            () => {
              if (signal.aborted || tornDown) return;
              onState(streamLostState(config));
              void teardown();
            },
          );
          return;
        }

        if (message.status === EventStatus.ERROR) {
          connectFailed = true;
          onState({
            status: "failed",
            message: streamEventMessage(
              message.info,
              "Kit App Streaming failed to start.",
            ),
            stream: null,
            capabilities: { video: false, input: false, messaging: false },
            detail: [`Stage: ${config.stage}`],
          });
        }
      },
      onStop: (message: { status: string; info?: string | Error }) => {
        if (signal.aborted || tornDown) return;
        if (message.status === EventStatus.ERROR) {
          onState({
            status: "failed",
            message: streamEventMessage(
              message.info,
              "The Kit stream stopped unexpectedly.",
            ),
            stream: null,
            capabilities: { video: false, input: false, messaging: false },
            detail: [],
          });
        }
      },
      onTerminate: () => {
        if (signal.aborted || tornDown) return;
        onState({
          status: "offline",
          message: "The Kit App Streaming session ended.",
          stream: null,
          capabilities: { video: false, input: false, messaging: false },
          detail: [],
        });
      },
    };

    try {
      await Promise.race([
        streamer.connect({
          streamSource: StreamType.DIRECT,
          streamConfig,
        }),
        rejectAfter(CONNECT_TIMEOUT_MS, signal, "Kit WebRTC connect timed out."),
      ]);
    } catch (error) {
      await teardown();
      signal.removeEventListener("abort", onAbort);
      onState({
        status: "failed",
        message:
          error instanceof Error
            ? `Could not connect to Kit App Streaming: ${error.message}`
            : "Could not connect to Kit App Streaming.",
        stream: null,
        capabilities: { video: false, input: false, messaging: false },
        detail: [
          `Signaling: ${config.signaling_url}`,
          "Confirm urbantwin_streaming.kit is running with --no-window and retry in Chromium.",
        ],
      });
      return inertConnection(
        "WebRTC connect threw before a session started.",
        resolveRunId,
      );
    }

    if (connectFailed) {
      await teardown();
      signal.removeEventListener("abort", onAbort);
      return inertConnection("Kit reported a stream start error.", resolveRunId);
    }

    if (!sawStartSuccess && !signal.aborted && !tornDown) {
      // connect() resolved without onStart SUCCESS — still wait briefly for media.
      void publishStreamWhenReady(
        mediaElements.video,
        signal,
        config,
        onState,
        () => {
          if (signal.aborted || tornDown) return;
          onState(streamLostState(config));
          void teardown();
        },
      );
    }

    return {
      async send(command) {
        return sendAllowListedViewCommand(resolveRunId(), command, streamer);
      },
      async close() {
        signal.removeEventListener("abort", onAbort);
        await teardown();
      },
    };
  },
};

/** Allow-list via API, then deliver over the WebRTC data channel when connected. */
export async function sendAllowListedViewCommand(
  runId: string,
  command: ViewCommand,
  streamer?: AppStreamer | null,
) {
  const apiResult = await api.view(runId, command);
  if (!apiResult.accepted) {
    return apiResult;
  }
  if (!streamer) {
    return {
      ...apiResult,
      delivered: false,
      reason:
        apiResult.reason ??
        "No active WebRTC session; the command passed the allow-list but was not sent to Kit.",
    };
  }
  try {
    await streamer.sendMessage({
      event_type: "urbantwin.view_command",
      payload: {
        state: command.state,
        camera: command.camera,
        overlay: command.overlay,
        playback: command.playback,
      },
    });
    return { accepted: true, delivered: true, command };
  } catch (error) {
    return {
      accepted: true,
      delivered: false,
      reason:
        error instanceof Error
          ? `Kit messaging failed: ${error.message}`
          : "Kit messaging failed.",
      command,
    };
  }
}

/**
 * Ask Kit to render at the on-screen video's aspect ratio, so the picture fills
 * the workspace instead of a 16:9 frame letterboxed into it.
 *
 * Not the library's `fitStreamResolution`: that clamps width and height
 * independently to the configured maximum, so a 1700x870 element becomes a
 * 1280x720 request and the aspect is lost. Here the element is scaled as a
 * whole into the 1280x720 pixel budget (never above device pixels), so the
 * GPU never renders more than it did before. Kit accepts this only with
 * /exts/omni.kit.livestream.app/primaryStream/allowDynamicResize=true, which
 * launch_urbantwin_streaming.bat passes.
 */
function fitStreamToElement(streamer: AppStreamer, video: HTMLVideoElement): () => void {
  let timer: number | undefined;
  let last = "";

  const apply = () => {
    // false = Kit said no; null = Kit has not answered, so try anyway.
    if (streamer.allowDynamicResize === false) return;
    const size = fittedStreamSize(video.clientWidth, video.clientHeight);
    if (!size) return;
    const key = `${size.width}x${size.height}`;
    if (key === last) return;
    last = key;
    streamer.resize(size.width, size.height).catch(() => {
      last = ""; // let the next resize retry
    });
  };

  const observer = new ResizeObserver(() => {
    window.clearTimeout(timer);
    timer = window.setTimeout(apply, FIT_DEBOUNCE_MS);
  });
  observer.observe(video);
  // Kit confirms dynamic-resize support shortly after the stream starts.
  const confirmTimer = window.setTimeout(apply, 1500);

  return () => {
    observer.disconnect();
    window.clearTimeout(timer);
    window.clearTimeout(confirmTimer);
  };
}

/** Element size scaled uniformly into the stream budget; multiples of 8 for the encoder. */
export function fittedStreamSize(
  clientWidth: number,
  clientHeight: number,
  pixelRatio = typeof window === "undefined" ? 1 : window.devicePixelRatio || 1,
): { width: number; height: number } | null {
  if (clientWidth < 64 || clientHeight < 64) return null;
  const scale = Math.min(STREAM_WIDTH / clientWidth, STREAM_HEIGHT / clientHeight, pixelRatio);
  const width = Math.floor((clientWidth * scale) / 8) * 8;
  const height = Math.floor((clientHeight * scale) / 8) * 8;
  return width >= 64 && height >= 64 ? { width, height } : null;
}

function offlineState(config: StreamConfig): ViewerState {
  return {
    status: "offline",
    message:
      config.reason ??
      "The server has no streaming session to offer, so no WebRTC connection was attempted.",
    stream: null,
    capabilities: { video: false, input: false, messaging: false },
    detail: [`Stage: ${config.stage}`],
  };
}

function resolveDirectEndpoints(config: StreamConfig): {
  signalingHost: string;
  signalingPort: number;
  mediaHost: string;
  mediaPort: number | null;
} | null {
  const signalingHost = config.signaling_host?.trim();
  const mediaHost = (config.media_host ?? config.signaling_host)?.trim();
  const signalingPort = config.signaling_port;
  const mediaPort =
    config.media_port == null ? null : Number(config.media_port);

  if (!signalingHost || !mediaHost || signalingPort == null) {
    return null;
  }

  if (mediaPort != null && !Number.isFinite(mediaPort)) {
    return null;
  }

  return { signalingHost, signalingPort, mediaHost, mediaPort };
}

function createHiddenMediaElements(): {
  video: HTMLVideoElement;
  audio: HTMLAudioElement;
  ownsVideo: boolean;
} {
  // NVIDIA's AppStreamer attaches its mouse / wheel / keyboard forwarding to the
  // element named by `videoElementId`. If that element is hidden, every click the
  // user makes lands on some *other* element and Kit receives no input at all.
  // So bind to the on-screen <video> the viewer renders whenever it is present,
  // and only fall back to a detached element (audio-only / tests) when it is not.
  const existing = document.getElementById(
    VIDEO_ELEMENT_ID,
  ) as HTMLVideoElement | null;

  const video = existing ?? document.createElement("video");
  const ownsVideo = existing === null;
  if (ownsVideo) {
    video.id = VIDEO_ELEMENT_ID;
    video.style.display = "none";
    document.body.appendChild(video);
  }
  video.playsInline = true;
  video.muted = true;
  video.autoplay = true;

  const audio = document.createElement("audio");
  audio.id = AUDIO_ELEMENT_ID;
  audio.autoplay = true;
  audio.style.display = "none";
  document.body.appendChild(audio);

  return { video, audio, ownsVideo };
}

function removeHiddenMediaElements(elements: {
  video: HTMLVideoElement;
  audio: HTMLAudioElement;
  ownsVideo: boolean;
}): void {
  elements.audio.srcObject = null;
  elements.audio.remove();
  // Only tear down a video element we created. The viewer's own element is
  // owned by React and must survive a reconnect.
  if (elements.ownsVideo) {
    elements.video.srcObject = null;
    elements.video.remove();
  }
}
async function publishStreamWhenReady(
  video: HTMLVideoElement,
  signal: AbortSignal,
  config: StreamConfig,
  onState: (state: ViewerState) => void,
  onStreamLost: () => void,
): Promise<void> {
  try {
    const stream = await waitForVideoMediaStream(
      video,
      signal,
      MEDIA_STREAM_WAIT_MS,
    );
    if (signal.aborted) return;

    onState({
      status: "connected",
      message: "Streaming from the RTX host.",
      stream,
      capabilities: { video: true, input: true, messaging: true },
      detail: [`Stage: ${config.stage}`, `Signaling: ${config.signaling_url}`],
    });
    watchForStreamLoss(stream, signal, onStreamLost);
  } catch (error) {
    if (signal.aborted) return;
    onState({
      status: "failed",
      message:
        error instanceof Error
          ? error.message
          : "Kit connected but no WebRTC MediaStream appeared on the video element.",
      stream: null,
      capabilities: { video: false, input: false, messaging: false },
      detail: [
        `Video element #${VIDEO_ELEMENT_ID} had no MediaStream in srcObject after ${MEDIA_STREAM_WAIT_MS}ms.`,
      ],
    });
  }
}

/**
 * Reads the MediaStream NVIDIA assigns to the off-DOM video element after SUCCESS.
 */
async function waitForVideoMediaStream(
  video: HTMLVideoElement,
  signal: AbortSignal,
  timeoutMs: number,
): Promise<MediaStream> {
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    if (signal.aborted) {
      throw new DOMException("aborted", "AbortError");
    }

    const srcObject = video.srcObject;
    if (
      srcObject instanceof MediaStream &&
      srcObject.getVideoTracks().some((track) => track.readyState === "live")
    ) {
      return srcObject;
    }

    await waitNextFrameOrDelay(50, signal);
  }

  throw new Error(
    `Timed out after ${timeoutMs}ms waiting for a MediaStream on #${VIDEO_ELEMENT_ID} (srcObject was ${describeSrcObject(video.srcObject)}).`,
  );
}

function watchForStreamLoss(
  stream: MediaStream,
  signal: AbortSignal,
  onStreamLost: () => void,
): void {
  let reported = false;
  const reportOnce = () => {
    if (reported || signal.aborted) return;
    reported = true;
    onStreamLost();
  };

  stream.addEventListener("inactive", reportOnce, { once: true });
  for (const track of stream.getVideoTracks()) {
    track.addEventListener("ended", reportOnce, { once: true });
  }
}

function streamLostState(config: StreamConfig): ViewerState {
  return {
    status: "failed",
    message: "The Omniverse video stream ended. Reconnecting automatically…",
    stream: null,
    capabilities: { video: false, input: false, messaging: false },
    detail: [`Stage: ${config.stage}`, `Signaling: ${config.signaling_url}`],
  };
}

function describeSrcObject(value: MediaProvider | null): string {
  if (value == null) return "null";
  if (value instanceof MediaStream) return "MediaStream";
  return value.constructor?.name ?? typeof value;
}

function waitNextFrameOrDelay(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("aborted", "AbortError"));
      return;
    }

    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve();
    };

    const timer = setTimeout(finish, ms);
    requestAnimationFrame(finish);

    signal.addEventListener(
      "abort",
      () => {
        settled = true;
        clearTimeout(timer);
        reject(new DOMException("aborted", "AbortError"));
      },
      { once: true },
    );
  });
}

function streamEventMessage(
  info: string | Error | undefined,
  fallback: string,
): string {
  if (info instanceof Error) return info.message || fallback;
  if (typeof info === "string" && info.trim().length > 0) return info;
  return fallback;
}

function rejectAfter(
  ms: number,
  signal: AbortSignal,
  message: string,
): Promise<never> {
  return new Promise((_, reject) => {
    if (signal.aborted) {
      reject(new DOMException("aborted", "AbortError"));
      return;
    }
    const timer = setTimeout(() => reject(new Error(message)), ms);
    signal.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(new DOMException("aborted", "AbortError"));
      },
      { once: true },
    );
  });
}

function inertConnection(
  reason: string,
  resolveRunId?: () => string,
): ViewerConnection {
  return {
    async send(command) {
      if (!resolveRunId) {
        return {
          accepted: false,
          delivered: false,
          reason,
          command,
        };
      }
      return sendAllowListedViewCommand(resolveRunId(), command);
    },
    async close() {
      /* nothing to tear down */
    },
  };
}
