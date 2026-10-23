import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");

const viewer = read("../components/OmniverseViewer.tsx");
const dashboard = read("../components/Dashboard.tsx");
const scenarioControls = read("../components/ScenarioControls.tsx");
const scenarioDrawer = read("../components/ScenarioDrawer.tsx");
const resultsDrawer = read("../components/ResultsDrawer.tsx");
const hazards = read("../components/HazardToolbar.tsx");
const header = read("../components/SiteHeader.tsx");
const styles = read("../app/globals.css");

test("workspace fills the window instead of scrolling the page", () => {
  assert.match(dashboard, /className="flex h-dvh flex-col overflow-hidden/);
  assert.match(dashboard, /<main className="relative min-h-0 flex-1 overflow-hidden">/);
});

test("viewport fills its box and letterboxes rather than crops the stream", () => {
  assert.doesNotMatch(viewer, /aspect-video/);
  assert.match(viewer, /absolute inset-0 size-full object-contain/);
  assert.doesNotMatch(viewer, /"[^"\n]*\bobject-cover\b[^"\n]*"/);
});

test("video sits alone in its wrapper, so AppStreamer's re-parenting cannot lift it over controls", () => {
  assert.match(
    viewer,
    /<div className="absolute inset-0 z-0">\s*<video\b[\s\S]*?\/>\s*<\/div>/,
  );
});

test("drawers are siblings of a single viewer, so layout changes never remount it", () => {
  assert.equal(dashboard.match(/<OmniverseViewer\b/g)?.length, 1);
  assert.ok(
    dashboard.indexOf("<OmniverseViewer") < dashboard.indexOf("<ScenarioDrawer"),
    "viewer renders before the drawers",
  );
});

test("before/after from any control is sent to Kit", () => {
  assert.match(viewer, /commandedStateRef\.current === state/);
});

test("scenario drawer stays mounted, inert when closed, and closes on Escape", () => {
  assert.match(scenarioDrawer, /inert=\{!open\}/);
  assert.match(dashboard, /event\.key !== "Escape"/);
  assert.match(scenarioDrawer, /Back to city/);
});

test("scenario fields use one column inside the fixed-width drawer", () => {
  assert.doesNotMatch(scenarioControls, /2xl:grid-cols-2/);
});

test("results body scrolls itself and stays mounted while collapsed", () => {
  assert.match(resultsDrawer, /hidden=\{!expanded\}/);
  assert.match(resultsDrawer, /overflow-y-auto/);
});

test("hazard lenses without a real 3D layer say so", () => {
  assert.match(hazards, /id: "flood",[\s\S]*?support: "metrics"/);
  assert.match(hazards, /id: "population",[\s\S]*?support: "planned"/);
  assert.doesNotMatch(
    hazards.match(/id: "flood",[\s\S]*?\},/)[0],
    /overlay:/,
    "flood must not switch to an overlay it does not have",
  );
});

test("header viewport status comes from the WebRTC adapter, not the TCP probe", () => {
  assert.match(header, /viewerStatus: ViewerState\["status"\]/);
  assert.match(dashboard, /onStatusChange=\{setViewerStatus\}/);
});

test("theme is light-only", () => {
  assert.doesNotMatch(styles, /prefers-color-scheme: dark/);
  assert.match(styles, /color-scheme: light/);
});
