import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The dev route badge sits bottom-left, on top of the results strip, and
  // every other corner holds workspace controls. Errors still surface.
  devIndicators: false,
  // demo_launch.ps1 opens http://127.0.0.1:3000. Next 16 blocks its dev websocket for that
  // origin unless listed, and Turbopack then never mounts lazily loaded components such as
  // the Omniverse viewer (blank viewport, "Viewport idle").
  allowedDevOrigins: ["127.0.0.1"],
};

export default nextConfig;
