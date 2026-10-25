"use client";

import { useEffect, useRef, useState } from "react";

import { Icon, type IconName } from "@/components/ui/Icon";
import { BEHAVIORS, BEHAVIOR_META } from "@/lib/behaviors";
import { cx } from "@/lib/cx";
import { VIEW_OVERLAYS, type ViewOverlay } from "@/lib/types";

export const OVERLAY_LABELS: Record<ViewOverlay, string> = {
  behavior: "Behavior",
  congestion: "Heat map",
  shade: "Interventions (After)",
  flood: "Flood (illustrative)",
  none: "City only",
};

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
    note: "Illustrative water over the streets. Depth and width scale with this run's flood-risk score, the same on every street (Pune has no elevation or per-street drainage data), so it shows how much water, not where it pools. Compare Before and After to see improved drainage.",
  },
  {
    id: "heat",
    label: "Heat",
    icon: "heat",
    support: "layer",
    overlay: "congestion",
    note: "Streets coloured by the mean heat exposure of the citizens who walked them in this run, for the arm shown (Before or After), on one fixed scale so the two compare. Agents are hidden. Rebuilt for every run (cities/pune/pune_view.py).",
  },
  {
    id: "mobility",
    label: "Mobility",
    icon: "mobility",
    support: "layer",
    overlay: "behavior",
    note: "Agents coloured by behaviour for the arm shown. In After, the run's interventions are drawn too: shade sails, drains or extra footpaths, at illustrative positions (the simulator applies them city-wide).",
  },
  {
    id: "population",
    label: "Population",
    icon: "population",
    support: "planned",
    note: "Planned. Population is a scenario input (an equivalent, not rendered agents); there is no population density layer.",
  },
];

const SUPPORT_LABEL = {
  layer: "3D layer",
  metrics: "Metrics only",
  planned: "Planned",
} as const;

/** Cool-to-hot ramp; the same stops as HEAT_RAMP in cities/pune/pune_view.py, which colours the 3D streets. */
const HEAT_RAMP =
  "linear-gradient(90deg, rgb(37 99 235), rgb(6 182 212) 35%, rgb(250 204 21) 65%, rgb(220 38 38))";

export function HazardToolbar({
  overlay,
  onOverlayChange,
}: {
  overlay: ViewOverlay;
  onOverlayChange: (overlay: ViewOverlay) => void;
}) {
  const [noteFor, setNoteFor] = useState<HazardId | null>(null);
  const [layersOpen, setLayersOpen] = useState(false);
  const layersRef = useRef<HTMLDivElement>(null);

  const active = HAZARDS.find((h) => h.overlay === overlay)?.id ?? null;
  const noteHazard = HAZARDS.find((h) => h.id === noteFor);

  useEffect(() => {
    if (!layersOpen) return;
    const onPointer = (event: PointerEvent) => {
      if (!layersRef.current?.contains(event.target as Node)) setLayersOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    return () => document.removeEventListener("pointerdown", onPointer);
  }, [layersOpen]);

  return (
    <div
      className="pointer-events-auto flex max-w-full flex-col items-start gap-2"
      onKeyDown={(event) => {
        if (event.key === "Escape" && (layersOpen || noteFor)) {
          event.preventDefault();
          setLayersOpen(false);
          setNoteFor(null);
        }
      }}
    >
      <div
        role="toolbar"
        aria-label="Hazard layers"
        className="flex max-w-full items-center gap-1 overflow-x-auto rounded-[12px] border border-hairline bg-surface/95 p-1 shadow-[var(--shadow-card)]"
      >
        {HAZARDS.map((hazard) => {
          const selected = active === hazard.id;
          const planned = hazard.support === "planned";
          return (
            <button
              key={hazard.id}
              type="button"
              aria-pressed={hazard.support === "layer" ? selected : undefined}
              aria-disabled={planned || undefined}
              aria-label={`${hazard.label}: ${SUPPORT_LABEL[hazard.support]}`}
              title={`${hazard.label} · ${SUPPORT_LABEL[hazard.support]}`}
              onClick={() => {
                if (hazard.overlay) onOverlayChange(hazard.overlay);
                // Every lens explains itself on click, so nothing depends on hover.
                setNoteFor((current) =>
                  current === hazard.id && !hazard.overlay ? null : hazard.id,
                );
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
              {hazard.support !== "layer" ? (
                <span
                  className={cx(
                    "hidden rounded-full px-1.5 py-px text-[11px] font-semibold uppercase tracking-[0.04em] md:inline",
                    planned ? "bg-neutral-soft text-ink-3" : "bg-caution-soft text-caution",
                  )}
                >
                  {SUPPORT_LABEL[hazard.support]}
                </span>
              ) : null}
            </button>
          );
        })}

        <span aria-hidden className="mx-0.5 h-5 w-px shrink-0 bg-hairline" />

        <div ref={layersRef} className="relative shrink-0">
          <button
            type="button"
            aria-expanded={layersOpen}
            aria-haspopup="true"
            onClick={() => setLayersOpen((v) => !v)}
            className={cx(
              "flex items-center gap-1.5 rounded-[9px] border px-2.5 py-1.5 text-[12px] font-medium transition-colors",
              layersOpen
                ? "border-accent-line bg-accent-soft text-accent"
                : "border-transparent text-ink-2 hover:bg-surface-2 hover:text-ink",
            )}
          >
            <Icon name="layers" />
            <span className="hidden sm:inline">{OVERLAY_LABELS[overlay]}</span>
            <span className="sr-only sm:hidden">Layers</span>
          </button>
        </div>
      </div>

      {layersOpen ? (
        <fieldset className="w-[min(260px,calc(100vw-2rem))] rounded-[12px] border border-hairline bg-surface p-2 shadow-[var(--shadow-lift)]">
          <legend className="sr-only">Viewport overlay</legend>
          <p className="px-2 pb-1.5 pt-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-3">
            Viewport overlay
          </p>
          {VIEW_OVERLAYS.map((option) => (
            <label
              key={option}
              className={cx(
                "flex cursor-pointer items-center gap-2 rounded-[8px] px-2 py-1.5 text-[12.5px] text-ink-2 hover:bg-surface-2",
                option === overlay && "bg-accent-soft text-accent",
              )}
            >
              <input
                type="radio"
                name="viewport-overlay"
                value={option}
                checked={option === overlay}
                onChange={() => {
                  onOverlayChange(option);
                  setNoteFor(null);
                  setLayersOpen(false);
                }}
                className="accent-[var(--accent)]"
              />
              {OVERLAY_LABELS[option]}
            </label>
          ))}
          <p className="px-2 pt-1.5 text-[11px] leading-relaxed text-ink-3">
            Interventions switches to After and draws this run&rsquo;s applied
            changes at illustrative positions; the simulator applies them city-wide.
          </p>
        </fieldset>
      ) : noteHazard ? (
        <div className="w-[min(360px,calc(100vw-2rem))] rounded-[12px] border border-hairline bg-surface/95 p-3 shadow-[var(--shadow-card)]">
          <div className="flex items-start gap-2">
            <p className="text-[12px] font-semibold text-ink">
              {noteHazard.label}
              <span className="ml-2 text-[11px] font-medium text-ink-3">
                {SUPPORT_LABEL[noteHazard.support]}
              </span>
            </p>
            <button
              type="button"
              onClick={() => setNoteFor(null)}
              aria-label="Dismiss note"
              className="-m-1 ml-auto rounded-[6px] p-1 text-ink-3 hover:text-ink"
            >
              <Icon name="close" className="size-3.5" />
            </button>
          </div>
          <p className="mt-1 text-[11.5px] leading-relaxed text-ink-2">{noteHazard.note}</p>
          {noteHazard.id === "heat" && active === "heat" ? <HeatLegend /> : null}
          {noteHazard.id === "mobility" && active === "mobility" ? <BehaviorKey /> : null}
        </div>
      ) : null}
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
