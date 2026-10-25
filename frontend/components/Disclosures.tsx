import { Card } from "@/components/ui/Card";
import type { CityFacts, Health } from "@/lib/types";

/** Fallback when an older recorded run lacks limitations. */
const PUNE_LIMITATIONS = [
  "Not a time-evolving crowd simulation. Walkers replay simulator routes at one equilibrium.",
  "Not a surveyed skyline: 40 of 2069 building heights come from OSM tags, the rest are interpolated or inferred.",
];

/**
 * Prototype limitations, kept visible but compact.
 *
 * Wording follows "Product language and integrity" in the handoff. Anything
 * removed from here has to be removed from the product claims too.
 */
export function Disclosures({
  health,
  city,
  stage,
}: {
  health: Health;
  city?: CityFacts;
  stage?: string;
}) {
  return (
    <Card className="bg-surface-2">
      <div className="grid gap-6 lg:grid-cols-3">
        <div>
          <h2 className="text-[13px] font-semibold tracking-[-0.01em] text-ink">
            What this prototype is
          </h2>
          <p className="mt-2 text-[12px] leading-relaxed text-ink-2">
            A deterministic pedestrian-experience simulation over real
            OpenStreetMap geometry, with survey-calibrated synthetic citizens and
            a deterministic advisor. Every figure is a prototype estimate.
          </p>
          {city ? (
            <p className="mt-2 text-[11px] leading-relaxed text-ink-3">
              {city.name}, from {city.source}: {city.zones} zones,{" "}
              {city.simulation_buildings} simulated buildings, {city.routes} routes,{" "}
              {city.visual_buildings} building meshes and {city.visual_trees} trees in
              the visual stage.
            </p>
          ) : null}
        </div>

        <div>
          <h2 className="text-[13px] font-semibold tracking-[-0.01em] text-ink">
            What it is not
          </h2>
          <ul className="mt-2 space-y-1.5 text-[12px] leading-relaxed text-ink-2">
            <li>
              Not a medical, meteorological, hydraulic or engineering model. Rain
              impact is a rainfall and flood-risk proxy, not a flood simulation.
            </li>
            <li>
              Not a prediction of what a specific person will do. The survey
              supports distributional consistency only, and its scenarios confound
              temperature, crowding and shade.
            </li>
            {(city?.limitations ?? PUNE_LIMITATIONS).map((text) => (
              <li key={text}>{text}</li>
            ))}
          </ul>
        </div>

        <div>
          <h2 className="text-[13px] font-semibold tracking-[-0.01em] text-ink">
            Where the numbers come from
          </h2>
          <p className="mt-2 text-[12px] leading-relaxed text-ink-2">
            {health.mode === "mock"
              ? "This deployment is serving recorded fixtures exported from a real simulator run. No HTTP backend, job queue or run database exists yet."
              : "This deployment is reading from the configured UrbanTwin AI backend."}
          </p>
          {stage ? (
            <p className="mt-2 font-mono text-[11px] leading-relaxed text-ink-3">
              stage: {stage}
            </p>
          ) : null}
          <p className="mt-2 text-[11px] leading-relaxed text-ink-3">
            {city?.key === "pune"
              ? "Pune animates straight from the simulator report and does not use the canonical snapshot contract (docs/PUNE_CITY.md); "
              : "The canonical visualisation contract is documented in docs/INTEGRATION_CONTRACT.md; "}
            the product contract this interface was built against is
            docs/FRONTEND_BACKEND_HANDOFF.md.
          </p>
        </div>
      </div>
    </Card>
  );
}
