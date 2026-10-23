import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The dev route badge sits bottom-left, on top of the results strip, and
  // every other corner holds workspace controls. Errors still surface.
  devIndicators: false,
};

export default nextConfig;
