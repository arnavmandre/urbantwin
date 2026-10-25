import type { Metadata, Viewport } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "UrbanTwin AI — Simulate the human experience before building the city",
  description:
    "A human-centric urban digital twin: deterministic pedestrian simulation over real OpenStreetMap geometry, survey-calibrated synthetic citizens and a deterministic advisor. Prototype estimates, not engineering models.",
};

export const viewport: Viewport = {
  themeColor: "#ffffff",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    // suppressHydrationWarning covers only this element's own attributes, which
    // browser extensions commonly add before React loads.
    <html lang="en-GB" suppressHydrationWarning>
      <head>
        {/* The workspace is deliberately light-only. Without this, the Dark
            Reader extension restyles every element (inline styles and data-
            attributes) before hydration, and React reports a mismatch on the
            whole tree. A literal tag, not `metadata`: metadata can stream in
            after the extension has already run. */}
        <meta name="darkreader-lock" />
      </head>
      <body className="antialiased">{children}</body>
    </html>
  );
}
