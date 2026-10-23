import { cx } from "@/lib/cx";

/**
 * Inline stroke icons. The project has no icon library, and one shape set of
 * ~10 glyphs does not justify adding one; these follow the same 24px grid and
 * stroke weight as the header mark.
 */
export type IconName =
  | "flood"
  | "heat"
  | "mobility"
  | "population"
  | "layers"
  | "sliders"
  | "close"
  | "chevron-up"
  | "chevron-down"
  | "expand"
  | "collapse"
  | "info"
  | "play"
  | "pause"
  | "restart";

const PATHS: Record<IconName, string[]> = {
  flood: [
    "M3 15c1.5 0 1.5-1 3-1s1.5 1 3 1 1.5-1 3-1 1.5 1 3 1 1.5-1 3-1 1.5 1 3 1",
    "M3 19c1.5 0 1.5-1 3-1s1.5 1 3 1 1.5-1 3-1 1.5 1 3 1 1.5-1 3-1 1.5 1 3 1",
    "M12 3c2.5 3 4 5 4 6.5a4 4 0 0 1-8 0C8 8 9.5 6 12 3z",
  ],
  heat: [
    "M14 14.76V4.5a2 2 0 0 0-4 0v10.26a4 4 0 1 0 4 0z",
    "M12 11v5",
  ],
  mobility: [
    "M5 19c3-6 11-2 14-8",
    "M5 19h.01",
    "M19 11h.01",
    "M9 5l2 2-2 2",
  ],
  population: [
    "M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
    "M3 20a6 6 0 0 1 12 0",
    "M16 11a2.5 2.5 0 1 0 0-5",
    "M18 20a5 5 0 0 0-3-4.6",
  ],
  layers: ["M12 3l9 5-9 5-9-5 9-5z", "M3 13l9 5 9-5", "M3 17.5l9 5 9-5"],
  sliders: [
    "M4 6h10",
    "M18 6h2",
    "M16 4v4",
    "M4 12h4",
    "M12 12h8",
    "M10 10v4",
    "M4 18h12",
    "M20 18h0",
    "M18 16v4",
  ],
  close: ["M6 6l12 12", "M18 6L6 18"],
  "chevron-up": ["M6 15l6-6 6 6"],
  "chevron-down": ["M6 9l6 6 6-6"],
  expand: ["M4 9V4h5", "M20 9V4h-5", "M4 15v5h5", "M20 15v5h-5"],
  collapse: ["M9 4v5H4", "M15 4v5h5", "M9 20v-5H4", "M15 20v-5h5"],
  info: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z", "M12 11v5", "M12 8h.01"],
  play: ["M8 5v14l11-7L8 5z"],
  pause: ["M9 5v14", "M15 5v14"],
  restart: ["M4 12a8 8 0 1 0 2.3-5.7", "M4 4v4h4"],
};

export function Icon({
  name,
  className,
}: {
  name: IconName;
  className?: string;
}) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cx("size-4 shrink-0", className)}
    >
      {PATHS[name].map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}
