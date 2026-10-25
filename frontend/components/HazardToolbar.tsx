"use client";

import { useState } from "react";

import { Icon, type IconName } from "@/components/ui/Icon";
import { BEHAVIORS, BEHAVIOR_META } from "@/lib/behaviors";
import { cx } from "@/lib/cx";
import type { ViewOverlay } from "@/lib/types";

type HazardId = "flood" | "heat" | "mobility" | "population";

/**
 * What each hazard lens can honestly show in the current system.
 *
 * - `layer`: an existing Kit overlay draws real data for it.
 * - `metrics`: the simulator reports it, but the scene has no 3D layer.
 * - `planned`: neither the simulator nor the scene provides it.
 *
 * Nothing here generates an overlay; a lens either switches to an overlay the
 * Kit `urbantwin.view_commands` handler already implements, or says why not.
 */
const HAZARDS: {
  id: HazardId;
  label: string;
  icon: IconName;
  support: "layer" | "metrics" | "planned";
  overlay?: ViewOverlay;
  note: string;
}[] = [
  {
    id: "flood",
    label: "Flood",
    icon: "flood",
    support: "layer",
    overlay: "flood",
    note: "Water over the streets, scaled by this run's flood risk. Compare Before and After to see what drainage changes. Illustrative: the risk is the same on every street (no elevation data), so it shows how much water, not where it pools.",
  },
  {
    id: "heat",
    label: "Heat",
    icon: "heat",
    support: "layer",
    overlay: "congestion",
    note: "Each street coloured by the average heat exposure of the citizens who walked it, on one scale for Before and After. People are hidden.",
  },
  {
    id: "mobility",
    label: "Mobility",
    icon: "mobility",
    support: "layer",
    overlay: "behavior",
    note: "Citizens walking their routes, coloured by what they decided to do.",
  },
  {
    id: "population",
    label: "Population",
    icon: "population",
    support: "planned",
    note: "Planned. Population is a scenario input (an equivalent, not rendered agents); there is no population density layer.",
  },
];

/** Cool-to-hot ramp; the same stops as HEAT_RAMP in cities/pune/pune_view.py, which colours the 3D streets. */
const HEAT_RAMP =
  "linear-gradient(90deg, rgb(37 99 235), rgb(6 182 212) 35%, rgb(250 204 21) 65%, rgb(220 38 38))";

/** What each intervention looks like in the 3D After view (cities/pune/pune_view.py LOOK_DEMO). */
const INTERVENTION_KEY: Record<string, { label: string; swatch: string; what: string }> = {
  shade_boost: { label: "Shade sails", swatch: "rgb(235 224 199)", what: "more shade on the hottest streets" },
  drainage_boost: { label: "Drains", swatch: "rgb(26 33 46)", what: "kerb drains for better drainage" },
  route_capacity_boost: {
    label: "Extra footpaths",
    swatch: "rgb(140 51 217)",
    what: "alternative pedestrian routes beside the busiest routes",
  },
};

export function HazardToolbar({
  overlay,
  onOverlayChange,
  state,
  applied,
}: {
  overlay: ViewOverlay;
  onOverlayChange: (overlay: ViewOverlay) => void;
  /** Arm on screen; in After the run's interventions are drawn and listed in the key. */
  state: "before" | "after";
  /** Intervention parameters the run applied (shade_boost, drainage_boost, route_capacity_boost). */
  applied: string[];
}) {
  const [keyOpen, setKeyOpen] = useState(true);
  const [plannedNote, setPlannedNote] = useState(false);
  const active = HAZARDS.find((h) => h.overlay === overlay) ?? HAZARDS.find((h) => h.id === "mobility")!;
  const drawn = state === "after" ? applied.filter((key) => INTERVENTION_KEY[key]) : [];

  return (
    <div className="pointer-events-auto flex max-w-full flex-col items-start gap-2">
      <div
        role="toolbar"
        aria-label="What the 3D view shows"
        className="flex max-w-full items-center gap-1 overflow-x-auto rounded-[12px] border border-hairline bg-surface/95 p-1 shadow-[var(--shadow-card)]"
      >
        {HAZARDS.map((hazard) => {
          const planned = hazard.support === "planned";
          const selected = !planned && active.id === hazard.id;
          return (
            <button
              key={hazard.id}
              type="button"
              aria-pressed={planned ? undefined : selected}
              aria-disabled={planned || undefined}
              title={planned ? `${hazard.label} · Planned` : hazard.label}
              onClick={() => {
                if (planned) {
                  setPlannedNote((v) => !v);
                  return;
                }
                setPlannedNote(false);
                setKeyOpen(true);
                if (hazard.overlay) onOverlayChange(hazard.overlay);
              }}
              className={cx(
                "flex shrink-0 items-center gap-1.5 rounded-[9px] border px-2.5 py-1.5 text-[12px] font-medium transition-colors",
                selected
                  ? "border-accent-line bg-accent-soft text-accent"
                  : "border-transparent text-ink-2 hover:bg-surface-2 hover:text-ink",
                planned && "text-ink-4 hover:text-ink-3",
              )}
            >
              <Icon name={hazard.icon} />
              <span className="hidden sm:inline">{hazard.label}</span>
              {planned ? (
                <span className="hidden rounded-full bg-neutral-soft px-1.5 py-px text-[11px] font-semibold uppercase tracking-[0.04em] text-ink-3 md:inline">
                  Planned
                </span>
              ) : null}
            </button>
          );
        })}
      </div>

      {plannedNote ? (
        <p className="w-[min(360px,calc(100vw-2rem))] rounded-[12px] border border-hairline bg-surface/95 p-3 text-[11.5px] leading-relaxed text-ink-2 shadow-[var(--shadow-card)]">
          {HAZARDS.find((h) => h.support === "planned")?.note}
        </p>
      ) : (
        <div className="w-[min(360px,calc(100vw-2rem))] rounded-[12px] border border-hairline bg-surface/95 p-3 shadow-[var(--shadow-card)]">
          <div className="flex items-center gap-2">
            <p className="text-[12px] font-semibold text-ink">
              {active.label}
              <span className="ml-2 text-[11px] font-medium text-ink-3">
                {state === "after" ? "After: with changes" : "Before: no changes"}
              </span>
            </p>
            <button
              type="button"
              onClick={() => setKeyOpen((v) => !v)}
              aria-expanded={keyOpen}
              className="ml-auto rounded-[6px] px-1.5 py-0.5 text-[11px] font-semibold text-accent hover:bg-accent-soft"
            >
              {keyOpen ? "Hide key" : "Show key"}
            </button>
          </div>
          {keyOpen ? (
            <>
              <p className="mt-1 text-[11.5px] leading-relaxed text-ink-2">{active.note}</p>
              {active.id === "heat" ? <HeatLegend /> : null}
              {active.id === "mobility" ? <BehaviorKey /> : null}
              {active.id === "flood" ? <FloodKey /> : null}
              {drawn.length > 0 ? (
                <div className="mt-2 border-t border-hairline pt-2">
                  <p className="text-[11px] font-semibold text-ink">Changes drawn in this After view</p>
                  <ul className="mt-1 space-y-1">
                    {drawn.map((key) => (
                      <li key={key} className="flex items-center gap-2 text-[11px] text-ink-2">
                        <span
                          aria-hidden
                          className="h-2.5 w-4 shrink-0 rounded-[3px] border border-hairline"
                          style={{ background: INTERVENTION_KEY[key].swatch }}
                        />
                        <span>
                          <span className="font-medium text-ink">{INTERVENTION_KEY[key].label}</span>:{" "}
                          {INTERVENTION_KEY[key].what}
                        </span>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-1 text-[11px] text-ink-3">
                    Positions are illustrative; the simulator applies each change city-wide.
                  </p>
                </div>
              ) : state === "before" && applied.length > 0 ? (
                <p className="mt-2 border-t border-hairline pt-2 text-[11px] text-ink-3">
                  Switch to After to see this run&rsquo;s changes drawn in the city.
                </p>
              ) : null}
            </>
          ) : null}
        </div>
      )}
    </div>
  );
}

function FloodKey() {
  return (
    <div className="mt-2 flex items-center gap-2 text-[11px] text-ink-2">
      <span aria-hidden className="h-2.5 w-6 shrink-0 rounded-[3px]" style={{ background: "rgb(15 64 107)" }} />
      Deeper, wider water = higher flood risk in this arm
    </div>
  );
}

function HeatLegend() {
  return (
    <div className="mt-2">
      <div className="h-2 w-full rounded-full" style={{ background: HEAT_RAMP }} />
      <div className="mt-1 flex justify-between text-[11px] text-ink-3">
        <span>20</span>
        <span>40</span>
        <span>60</span>
        <span>80 heat exposure</span>
      </div>
    </div>
  );
}

function BehaviorKey() {
  return (
    <ul className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1">
      {BEHAVIORS.map((id) => (
        <li key={id} className="flex items-center gap-1.5 text-[11px] text-ink-2">
          <span
            aria-hidden
            className="size-2 shrink-0 rounded-full"
            style={{ background: BEHAVIOR_META[id].hex }}
          />
          {BEHAVIOR_META[id].label}
        </li>
      ))}
    </ul>
  );
}
