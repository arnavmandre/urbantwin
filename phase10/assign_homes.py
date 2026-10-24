"""
Phase 10 step 4 - give the synthetic citizens somewhere to live and go.

`generate_citizens.py` produces behaviour, not geography. The simulator also
needs `home` and `destination` building ids with a route between them, so this
attaches them for a chosen city file and writes a citizens file that loads.

Homes are drawn from buildings with capacity 0 (pure origins); destinations are
drawn from buildings that have capacity, weighted by it - a 5,000-capacity
transit hub receives more trips than a 400-capacity shop. Only pairs that
actually have a route are used, so the output always passes the simulator's own
validation.

Trip assignment is NOT survey data. The survey asked how people feel in an
environment, not where they commute. This step is a documented trip-distribution
heuristic; the behavioural parameters are the calibrated part.

Run:
    python phase10/assign_homes.py                         # against the Pune city
    python phase10/assign_homes.py --city city.json        # 8-building demo
    python phase10/assign_homes.py --count 400 --out ../Simulation/citizens_survey.json
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SIM = ROOT / "Simulation"
SOURCE = SIM / "citizens_survey.json"

REQUIRED = ("heat_tolerance", "rain_tolerance", "crowd_tolerance",
            "walking_speed_kmh", "green_preference", "transit_preference")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--city", default="../cities/pune/city_pune.json",
                    help="city file relative to Simulation/ (default: ../cities/pune/city_pune.json)")
    ap.add_argument("--source", type=Path, default=SOURCE)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--count", type=int, default=None,
                    help="use a subset; default is every generated citizen")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    city_path = SIM / args.city
    city = json.loads(city_path.read_text(encoding="utf-8"))
    payload = json.loads(args.source.read_text(encoding="utf-8"))
    citizens = payload["citizens"]
    if args.count:
        citizens = citizens[:args.count]

    # Which destinations are reachable from which origin, per the real routes.
    reachable = collections.defaultdict(list)
    for r in city["routes"]:
        reachable[r["start"]].append(r["end"])
        reachable[r["end"]].append(r["start"])

    capacity = {b["id"]: b["capacity"] for b in city["buildings"]}
    homes = [b["id"] for b in city["buildings"]
             if b["capacity"] == 0 and reachable.get(b["id"])]
    if not homes:
        # Some city files give every building a capacity; fall back to
        # residential type.
        homes = [b["id"] for b in city["buildings"]
                 if b.get("type") == "residential" and reachable.get(b["id"])]
    if not homes:
        raise SystemExit(f"{city_path.name}: no origin buildings with routes")

    rng = np.random.default_rng(args.seed)
    home_draw = rng.integers(0, len(homes), size=len(citizens))

    placed, skipped = [], 0
    for i, c in enumerate(citizens):
        home = homes[int(home_draw[i])]
        options = [d for d in dict.fromkeys(reachable[home]) if capacity.get(d, 0) > 0]
        if not options:
            skipped += 1
            continue
        weights = np.array([capacity[d] for d in options], dtype=float)
        weights /= weights.sum()
        dest = options[int(rng.choice(len(options), p=weights))]
        placed.append({
            "id": c["id"],
            "archetype": c["archetype"],
            "home": home,
            "destination": dest,
            **{k: c[k] for k in REQUIRED},
            "weight": c.get("weight", 1.0),
        })

    if not placed:
        raise SystemExit("no citizen could be placed - check the city file's routes")

    out = args.out or (SIM / f"citizens_survey_{Path(args.city).stem}.json")
    out.write_text(json.dumps({
        "schema_version": 1,
        "description": (
            f"Survey-calibrated synthetic citizens placed on {city_path.name}. "
            "Behavioural parameters are calibrated from 41 real participants "
            "(see phase10/). Home/destination assignment is a documented trip "
            "heuristic, NOT survey data."
        ),
        "source": payload.get("source", {}),
        "city_file": city_path.name,
        "citizens": placed,
    }, indent=2) + "\n", encoding="utf-8")

    dests = collections.Counter(c["destination"] for c in placed)
    names = {b["id"]: b.get("name", b["id"]) for b in city["buildings"]}
    print(f"placed {len(placed)} citizens on {city_path.name}"
          + (f" ({skipped} skipped - no reachable destination)" if skipped else ""))
    print(f"  {len(homes)} origin buildings, {len(dests)} destinations used")
    print("  busiest destinations:")
    for bid, n in dests.most_common(5):
        print(f"    {names.get(bid, bid)[:40]:42s} {n}")
    print(f"\nwrote {out}")
    print(f"\nRun it:  cd Simulation && python main.py {out.name} {city_path.name}")


if __name__ == "__main__":
    main()
