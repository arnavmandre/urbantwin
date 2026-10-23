import type {
  ViewerAdapter,
  ViewerConnectContext,
  ViewerConnection,
} from "./adapter";

/**
 * The offline viewport adapter.
 *
 * Selected whenever `/api/stream/config` does not advertise a Kit session:
 * always in mock mode (recorded fixtures never stream), and in live mode while
 * Kit signaling is not listening. It deliberately produces no picture and
 * reports offline with the reason that applies. The real connection is
 * `kit-webrtc-adapter.ts`.
 */
export const mockViewerAdapter: ViewerAdapter = {
  id: "placeholder-offline",
  displayName: "Offline viewport",
  transportLabel: "No stream · offline",

  async connect(ctx: ViewerConnectContext): Promise<ViewerConnection> {
    const { config, onState, signal } = ctx;

    onState({
      status: "connecting",
      message: "Checking for a streaming session\u2026",
      stream: null,
      capabilities: { video: false, input: false, messaging: false },
      detail: [],
    });

    // A short, visible probe so the connecting state is real rather than a
    // decorative spinner.
    await wait(450, signal);
    if (signal.aborted) throw new DOMException("aborted", "AbortError");

    if (config.status === "offline") {
      // Recorded fixtures carry their own historical reason text; in mock mode
      // the accurate statement is simply that mock mode does not stream.
      const mock = config.source === "recorded_fixture";
      onState({
        status: "offline",
        message: mock
          ? "3D streaming is unavailable in mock mode. Recorded fixtures have no Kit session."
          : (config.reason ?? "No Kit streaming session is available right now."),
        stream: null,
        capabilities: { video: false, input: false, messaging: false },
        detail: [
          mock
            ? "To stream, point URBANTWIN_API_BASE at the Python API and start the Kit streaming app."
            : "",
          `Stage: ${config.stage}`,
          config.desktop_fallback ? `Desktop editor: ${config.desktop_fallback}` : "",
        ].filter(Boolean),
      });
    } else {
      // The server said a session exists but this adapter cannot open one.
      onState({
        status: "failed",
        message:
          "A streaming session was advertised, but the placeholder adapter cannot open WebRTC. Enable the NVIDIA client adapter.",
        stream: null,
        capabilities: { video: false, input: false, messaging: false },
        detail: [`Signaling: ${config.signaling_url ?? "unknown"}`],
      });
    }

    return {
      async send(command) {
        return {
          accepted: false,
          delivered: false,
          reason:
            "The viewport is offline (no Kit session), so view commands are not delivered.",
          command,
        };
      },
      async close() {
        /* nothing to tear down */
      },
    };
  },
};

function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
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
