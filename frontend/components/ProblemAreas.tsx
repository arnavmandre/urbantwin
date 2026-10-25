"use client";

import { useState } from "react";

import { Card, CardHeader } from "@/components/ui/Card";
import { Pill } from "@/components/ui/Pill";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { cx } from "@/lib/cx";
import { formatCount } from "@/lib/metric-format";
import type { RunState, RunStateSummary } from "@/lib/types";

type Tab = "buildings" | "routes" | "zones";

const SHOWN = 8;

/**
 * Problem zones, buildings and routes, straight from the simulator's structured
 * output. Nothing here is written by the frontend.
 */
export function ProblemAreas({
  summary,
  state,
}: {
  summary: RunStateSummary;
  state: RunState;
}) {
  const [tab, setTab] = useState<Tab>("buildings");
  const [expanded, setExpanded] = useState(false);

  const buildings = summary.problem_buildings;
  const routes = summary.problem_routes;
  const zones = summary.problem_zones;

  const visibleBuildings = expanded ? buildings : buildings.slice(0, SHOWN);

  return (
    <Card>
      <CardHeader
        eyebrow="Pressure points"
        title="Problem areas"
        description={`Flagged by the simulator in the ${state} state of this run.`}
        actions={
          <SegmentedControl<Tab>
            ariaLabel="Problem area category"
            size="sm"
            value={tab}
            onChange={setTab}
            segments={[
              { value: "buildings", label: `Buildings ${buildings.length}` },
              { value: "routes", label: `Routes ${routes.length}` },
              { value: "zones", label: `Zones ${zones.length}` },
            ]}
          />
        }
      />

      {tab === "buildings" ? (
        <>
          <ul className="mt-5 grid gap-2 lg:grid-cols-2">
            {visibleBuildings.map((building) => (
              <li
                key={building.id}
                className="rounded-[12px] border border-hairline bg-surface-2 p-3"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-[13px] font-medium text-ink">
                      {displayName(building)}
                    </p>
                    <p className="text-[11px] text-ink-3">
                      {building.zone} &middot;{" "}
                      <span className="font-mono">{building.id}</span>
                    </p>
                  </div>
                  <Pill tone={severityTone(building.severity)}>
                    {building.severity.toFixed(0)} severity
                  </Pill>
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  {building.issues.map((issue) => (
                    <span
                      key={issue}
                      className="rounded-full bg-surface-3 px-2 py-0.5 text-[11px] text-ink-2"
                    >
                      {issue}
                    </span>
                  ))}
                </div>
                <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-surface-3">
                  <div
                    className={cx(
                      "h-full rounded-full",
                      building.severity >= 90
                        ? "bg-negative"
                        : building.severity >= 70
                          ? "bg-caution"
                          : "bg-ink-4",
                    )}
                    style={{ width: `${Math.min(100, building.severity)}%` }}
                  />
                </div>
              </li>
            ))}
          </ul>
          {buildings.length > SHOWN ? (
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="mt-3 text-[12px] font-semibold text-accent transition-opacity hover:opacity-80"
            >
              {expanded
                ? "Show fewer"
                : `Show all ${formatCount(buildings.length)} flagged buildings`}
            </button>
          ) : null}
        </>
      ) : null}

      {tab === "routes" ? (
        <ul className="mt-5 grid gap-2 lg:grid-cols-2">
          {routes.map((route) => (
            <li
              key={route.id}
              className="flex items-center justify-between gap-3 rounded-[12px] border border-hairline bg-surface-2 p-3"
            >
              <div className="min-w-0">
                <p className="truncate text-[13px] font-medium text-ink">
                  <span className="font-mono">{route.id}</span>{" "}
                  <span className="font-normal text-ink-3">
                    {route.from} &rarr; {route.to}
                  </span>
                </p>
                <p className="text-[11px] text-ink-3">{route.via_zones.join(", ")}</p>
              </div>
              <Pill tone={severityTone(route.crowding * 2)}>
                {route.crowding.toFixed(1)} crowding
              </Pill>
            </li>
          ))}
          {routes.length === 0 ? <Empty>No routes were flagged.</Empty> : null}
        </ul>
      ) : null}

      {tab === "zones" ? (
        <ul className="mt-5 grid gap-2 lg:grid-cols-2">
          {zones.map((zone) => (
            <li
              key={zone}
              className="rounded-[12px] border border-hairline bg-surface-2 px-3 py-2.5 text-[13px] text-ink"
            >
              {zone}
            </li>
          ))}
          {zones.length === 0 ? <Empty>No zones were flagged.</Empty> : null}
        </ul>
      ) : null}

      <p className="mt-4 text-[11px] leading-relaxed text-ink-3">
        Severity is a heuristic prototype score, not an engineering assessment.
        Building names and positions come from OpenStreetMap; some attributes are
        inferred.
      </p>
    </Card>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <li className="col-span-full rounded-[12px] border border-dashed border-hairline px-3 py-6 text-center text-[12px] text-ink-3">
      {children}
    </li>
  );
}

/** OSM buildings without a name tag arrive named by their id; the id stays in the line below. */
function displayName(building: { id: string; name: string }) {
  const name = building.name?.trim();
  return name && name !== building.id && !/^(way|node|relation)_\d+$/.test(name)
    ? name
    : "Unnamed building";
}

function severityTone(severity: number) {
  if (severity >= 90) return "negative" as const;
  if (severity >= 70) return "caution" as const;
  return "neutral" as const;
}
