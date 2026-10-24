"""
Phase 10 step 3 - grow 41 real participants into a synthetic population.

The rule from the brief: do not copy one real person a thousand times. Learn the
population-level pattern and sample from it.

Method - a Gaussian copula:

  1. Push each bounded parameter through a logit so it lives on the whole real
     line (walking speed is standardised instead, it is not a 0-1 quantity).
  2. Estimate the mean vector AND the full covariance matrix across the 41
     fitted participants.
  3. Draw from that multivariate normal.
  4. Invert the transforms to land back in range.

Step 2 is the point. Sampling each parameter independently would manufacture
citizens who are heat-sensitive AND crowd-loving AND fast-walking - combinations
nobody in the sample exhibited. The covariance keeps the real structure, e.g.
the observed -0.30 between heat tolerance and green preference: people who
suffer in heat care more about trees.

Categorical traits (age band, self-rated heat sensitivity) are drawn from the
observed frequencies, conditioned so that an elderly citizen does not come out
walking at 6.7 km/h.

Run:  python phase10/generate_citizens.py [--count 1000] [--seed 7]
Out:  phase10/data/synthetic_citizens.csv
      Simulation/citizens_survey.json   (simulator schema, ready to run)
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import math
import re
import hashlib
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = HERE / "data"
FITTED = DATA / "participant_parameters.csv"
OUT_CSV = DATA / "synthetic_citizens.csv"
OUT_JSON = ROOT / "Simulation" / "citizens_survey.json"

UNIT = ["heat_tolerance", "rain_tolerance", "crowd_tolerance",
        "green_preference", "transit_preference"]
SPEED = "walking_speed_kmh"
SPEED_RANGE = (1.8, 7.2)

# Archetype naming is a reporting label only - it never feeds the simulation.
def archetype(row) -> str:
    if row["age_mid"] >= 60:
        return "Elderly citizen"
    if row[SPEED] < 3.6:
        return "Mobility-limited citizen"
    if row["transit_preference"] > 0.6:
        return "Transit-dependent citizen"
    if row["heat_tolerance"] > 0.72:
        return "Outdoor worker"
    if row["age_mid"] <= 24:
        return "Student"
    if row["green_preference"] > 0.85:
        return "Family / parent"
    return "General pedestrian"


def logit(p, eps=1e-3):
    p = np.clip(p, eps, 1 - eps)
    return np.log(p / (1 - p))


def expit(x):
    return 1.0 / (1.0 + np.exp(-x))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("responses", nargs="?", type=Path, help="new Q1-Q16 form CSV; otherwise use the legacy fitted data")
    ap.add_argument("--option-counts", type=Path)
    ap.add_argument("--out-dir", type=Path, default=DATA / "new_survey")
    ap.add_argument("--count", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=7,
                    help="fixed so the population is reproducible")
    args = ap.parse_args()
    if args.count < 1:
        ap.error("--count must be positive")
    if args.responses:
        build_form_population(args.responses, args.option_counts, args.out_dir, args.count, args.seed)
        return

    with FITTED.open(encoding="utf-8") as f:
        fitted = list(csv.DictReader(f))
    if len(fitted) < 5:
        raise SystemExit("not enough fitted participants to estimate a covariance")
    print(f"{len(fitted)} real participants -> {args.count} synthetic citizens")

    AGE_MID = {"Under 18": 16, "18-24": 21, "25-34": 29, "35-44": 39,
               "45-59": 52, "60+": 66}

    # --- observed joint distribution ------------------------------------
    unit_obs = np.array([[float(r[k]) for k in UNIT] for r in fitted])
    speed_obs = np.array([float(r[SPEED]) for r in fitted])

    z = np.column_stack([logit(unit_obs), speed_obs])
    mean = z.mean(axis=0)
    # rowvar=False -> columns are variables. Small sample, so nudge the diagonal
    # to keep the matrix positive definite for the Cholesky factor.
    cov = np.cov(z, rowvar=False) + np.eye(z.shape[1]) * 1e-6

    rng = np.random.default_rng(args.seed)
    draws = rng.multivariate_normal(mean, cov, size=args.count)

    unit_new = expit(draws[:, :len(UNIT)])
    speed_new = np.clip(draws[:, len(UNIT)], *SPEED_RANGE)

    # --- categorical traits from observed frequencies --------------------
    ages = [r["age_group"] for r in fitted]
    age_counts = collections.Counter(ages)
    age_labels = list(age_counts)
    age_p = np.array([age_counts[a] for a in age_labels], dtype=float)
    age_p /= age_p.sum()
    age_draw = rng.choice(len(age_labels), size=args.count, p=age_p)

    # Older citizens should not inherit a young walking speed. Shift each
    # sampled speed toward the observed mean for its own age band.
    band_speed = collections.defaultdict(list)
    for r in fitted:
        band_speed[r["age_group"]].append(float(r[SPEED]))
    band_mean = {a: float(np.mean(v)) for a, v in band_speed.items()}
    overall = float(speed_obs.mean())

    rows = []
    for i in range(args.count):
        age = age_labels[age_draw[i]]
        shift = band_mean.get(age, overall) - overall
        speed = float(np.clip(speed_new[i] + 0.7 * shift, *SPEED_RANGE))
        row = {
            "citizen_id": f"C{i + 1:05d}",
            "age_group": age,
            "age_mid": AGE_MID.get(age, 30),
            SPEED: round(speed, 2),
        }
        for j, k in enumerate(UNIT):
            row[k] = round(float(unit_new[i, j]), 3)
        row["archetype"] = archetype(row)
        rows.append(row)

    fields = ["citizen_id", "archetype", "age_group", "age_mid", SPEED] + UNIT
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    # --- simulator schema -------------------------------------------------
    # home/destination are filled in by whichever city file this is run against;
    # assign_homes.py does that. Written here without them would fail validation,
    # so emit the behavioural half only and let the assigner place them.
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "description": (
            "Synthetic citizens calibrated to 41 real survey participants "
            "(Gaussian copula over logit-transformed parameters, preserving the "
            "observed covariance). Behavioural parameters only - run "
            "phase10/assign_homes.py to attach home/destination for a given "
            "city file. Prototype calibration, not a validated behavioural model."
        ),
        "source": {
            "participants": len(fitted),
            "scenarios_per_participant": 4,
            "observations": len(fitted) * 4,
            "method": "gaussian copula on logit-transformed fitted parameters",
            "seed": args.seed,
        },
        "citizens": [
            {"id": r["citizen_id"], "archetype": r["archetype"],
             "age_group": r["age_group"],
             **{k: r[k] for k in UNIT}, SPEED: r[SPEED], "weight": 1.0}
            for r in rows
        ],
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {OUT_CSV}")
    print(f"wrote {OUT_JSON}\n")
    for k in UNIT + [SPEED]:
        real = np.array([float(r[k]) for r in fitted])
        syn = np.array([r[k] for r in rows])
        print(f"  {k:20s} real {real.mean():5.2f}+-{real.std():4.2f}   "
              f"synthetic {syn.mean():5.2f}+-{syn.std():4.2f}")
    print("\n  archetypes:", dict(collections.Counter(r["archetype"] for r in rows)))
    print("\nNext: python phase10/assign_homes.py   (attach home/destination)")


# New-form mode keeps the original 41-person generation path and its outputs intact.
AGE_BANDS = ["18–24", "25–34", "35–59", "60 or above"]
COMFORT = dict(zip(["Very uncomfortable", "Slightly uncomfortable", "Comfortable", "Very comfortable"], np.linspace(0, 1, 4)))
WILLING = dict(zip(["Definitely would not", "Probably would not", "Probably would", "Definitely would"], np.linspace(0, 1, 4)))
DETOUR = dict(zip(["No extra time", "Up to 5 minutes", "6–10 minutes", "More than 10 minutes"], np.linspace(0, 1, 4)))
FORM_OPTIONS = {
    1: dict(zip(AGE_BANDS, range(4))),
    2: {"Under 10 minutes": 6.7, "10–15 minutes": 4.8, "16–20 minutes": 3.3, "Over 20 minutes": 2.6},
    3: {"Almost daily": 1., "Weekly": 2/3, "Monthly": 1/3, "Rarely or never": 0.},
    4: {"Not at all": 1., "A little": 2/3, "Quite a bit": 1/3, "A lot": 0.},
    5: COMFORT, 6: COMFORT, 7: DETOUR, 8: COMFORT, 9: DETOUR,
    10: WILLING, 11: WILLING, 12: DETOUR,
    13: {"Take the dry route": 1., "Use available public transport": 2/3, "Wait somewhere safe": 1/3, "Delay or cancel the trip": 0.},
    14: {"A 15-minute route with trees and gardens": 1., "A 10-minute route with little greenery": 0., "Either route is fine": .5, "I would avoid walking": np.nan},
    15: DETOUR, 16: WILLING,
}
FORM_VARIABLES = UNIT + [SPEED, "age_band"]
FORM_ITEMS = [((4, False), (5, False), (6, False), (7, True)),
              ((10, False), (11, False), (12, True), (13, False)),
              ((8, False), (9, True)), ((14, False), (15, False)),
              ((3, False), (16, False)), ((2, False),), ((1, False),)]
# Diagnostic tolerances fixed before reading results; no claim of behavioural validity.
FORM_GATES = {"ks": .25, "mean_unit": .12, "sd_unit": .12, "mean_speed": .8,
              "sd_speed": .8, "coverage_low": .85, "coverage_high": 1.}


def canonical_answer(value):
    s = " ".join(str(value or "").strip().split())
    s = re.sub(r"(?<=\d)[–—-](?=\d)", "–", s)
    if s in ("", "No answer"):
        return ""
    return s.replace("Use available public transport (bus, metro, train)", "Use available public transport")


def read_form(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        columns = {}
        for key in reader.fieldnames or []:
            match = re.match(r"^(?:Q)?(\d+)(?:\.|\s|$)", key)
            if match and 1 <= int(match[1]) <= 16:
                q = int(match[1])
                if q in columns:
                    raise ValueError(f"duplicate question column Q{q}")
                columns[q] = key
        if set(columns) != set(range(1, 17)):
            raise ValueError("Need respondent-level Q1–Q16 columns; option counts cannot fit a copula.")
        rows = list(reader)
    answers = {q: [canonical_answer(row.get(col)) for row in rows] for q, col in columns.items()}
    invalid = [f"row {i+2}, Q{q}" for q, values in answers.items() for i, value in enumerate(values)
               if value and value not in FORM_OPTIONS[q]]
    if invalid:
        raise ValueError("Unparseable answers (values withheld): " + "; ".join(invalid))
    if len(rows) < 15:
        raise ValueError("Need at least 15 respondents for the requested repeated holdouts.")
    return answers


def map_form(answers):
    scored = {q: np.array([FORM_OPTIONS[q].get(v, np.nan) for v in values], dtype=float)
              for q, values in answers.items()}
    mapped, used = [], []
    for items in FORM_ITEMS:
        vals = np.column_stack([1-scored[q] if reverse else scored[q] for q, reverse in items])
        n = np.isfinite(vals).sum(axis=1)
        mapped.append(np.divide(np.nansum(vals, axis=1), n, out=np.full(len(n), np.nan), where=n>0))
        used.append(n)
    x = np.column_stack(mapped)
    x[:, :5] = np.clip(x[:, :5], .02, .98)
    return x, np.column_stack(used)


def finite_corr(x):
    centered = x - np.mean(x, axis=0)
    norms = np.linalg.norm(centered, axis=0)
    corr = np.divide(centered.T @ centered, np.outer(norms, norms),
                     out=np.zeros((x.shape[1], x.shape[1])), where=np.outer(norms, norms)>1e-12)
    np.fill_diagonal(corr, 1.)
    return corr


def normal_scores(x):
    from scipy.stats import norm, rankdata
    return np.column_stack([norm.ppf((rankdata(col, method="average")-.5)/len(col)) for col in x.T])


def fit_normal_copula(x):
    if np.any(~np.isfinite(x).any(axis=0)):
        raise ValueError("A variable has no observed training values; cannot impute or fit it.")
    medians = np.nanmedian(x, axis=0)
    if not np.isfinite(medians).all():
        raise ValueError("A variable has no observed training values; cannot impute or fit it.")
    complete = np.where(np.isfinite(x), x, medians)
    corr = finite_corr(normal_scores(complete))
    eigen, vectors = np.linalg.eigh(corr)
    corrected = bool(np.min(eigen) < 1e-6)
    if corrected:
        corr = (vectors * np.maximum(eigen, 1e-6)) @ vectors.T
        corr /= np.sqrt(np.outer(np.diag(corr), np.diag(corr)))
    return {"correlation": corr, "medians": medians, "marginals": [np.sort(col[np.isfinite(col)]) for col in x.T],
            "corrected": corrected}


def draw_normal_copula(model, count, rng, independent=False):
    from scipy.stats import norm
    corr = np.eye(len(model["medians"])) if independent else model["correlation"]
    u = norm.cdf(rng.multivariate_normal(np.zeros(len(corr)), corr, count))
    samples = np.column_stack([np.quantile(col, u[:, j], method="linear") for j, col in enumerate(model["marginals"])])
    if len(corr) == 7:
        # Age is a category: an empirical inverse CDF preserves existing bands without interpolating codes.
        age = model["marginals"][6]
        samples[:, 6] = age[np.minimum((u[:, 6]*len(age)).astype(int), len(age)-1)]
    return samples


def heldout_metrics(synthetic, heldout):
    from scipy.stats import ks_2samp, wasserstein_distance
    per = []
    for j in range(6):
        real = heldout[np.isfinite(heldout[:, j]), j]
        syn = synthetic[:, j]
        if len(real) < 2:
            per.append([np.nan]*4)
        else:
            per.append([ks_2samp(real, syn).statistic, wasserstein_distance(real, syn),
                        syn.mean()-real.mean(), syn.std(ddof=1)-real.std(ddof=1)])
    real = heldout[np.isfinite(heldout).all(axis=1)]
    if len(real) < 3:
        return np.array(per), np.array([np.nan]*3), 0
    mask = np.triu(np.ones((7, 7), dtype=bool), 1)
    varying = np.std(real, axis=0) > 1e-10
    mask &= np.outer(varying, varying)
    difference = finite_corr(normal_scores(synthetic))-finite_corr(normal_scores(real))
    delta = difference[mask]
    # Express both sets in the synthetic model's units before computing its 95% ellipsoid.
    mean, scale = synthetic.mean(axis=0), np.maximum(synthetic.std(axis=0), 1e-6)
    centered = (synthetic-mean)/scale
    inverse = np.linalg.pinv(np.cov(centered, rowvar=False)+np.eye(7)*1e-6)
    distance = np.einsum("ij,jk,ik->i", centered, inverse, centered)
    test = (real-mean)/scale
    test_distance = np.einsum("ij,jk,ik->i", test, inverse, test)
    return np.array(per), np.array([np.max(np.abs(delta)) if len(delta) else np.nan,
                                     np.sqrt(2*np.sum(delta**2)), np.mean(test_distance<=np.quantile(distance, .95))]), int(mask.sum())


def validate_form(x, seed, count):
    repeats, splits = [], []
    for repeat in range(20):
        rng = np.random.default_rng(np.random.SeedSequence([seed, 100, repeat]))
        order = rng.permutation(len(x))
        test_size = int(math.ceil(.2*len(x)))
        test, train = order[:test_size], order[test_size:]
        model = fit_normal_copula(x[train])
        splits.append({"repeat": repeat+1, "training_rows": (train+1).tolist(), "holdout_rows": (test+1).tolist(),
                       "positive_definite_correction": model["corrected"]})
        row = {}
        for method in ("copula", "independent"):
            # Same underlying seed and training marginals for a paired comparison.
            draws = draw_normal_copula(model, count, np.random.default_rng(np.random.SeedSequence([seed, 200, repeat])), method=="independent")
            per, joint, pairs = heldout_metrics(draws, x[test])
            row[method] = {"per_parameter": per.tolist(), "joint": joint.tolist(), "correlation_pairs_evaluable": pairs}
        repeats.append(row)
    return repeats, splits


def counts_audit(path, answers):
    if path is None:
        return [], False, False
    with path.open(encoding="utf-8-sig", newline="") as f:
        lines = list(csv.reader(f))
    start = next((i for i, row in enumerate(lines) if "New form selections" in row), None)
    if start is None:
        raise ValueError("Counts file has no 'New form selections' column")
    col = lines[start].index("New form selections")
    expected = {}
    for row in lines[start+1:]:
        if not row or not row[0].strip():
            continue
        match = re.match(r"^(\d+)\.", row[0])
        if not match:
            raise ValueError("Invalid counts question")
        key = (int(match[1]), canonical_answer(row[1]))
        if key in expected:
            raise ValueError("Duplicate counts category")
        expected[key] = int(row[col])
    actual = {(q, value): count for q, values in answers.items() for value, count in collections.Counter(values).items()}
    keys = sorted(set(expected)|set(actual))
    rows = [[q, answer or "No answer", expected.get((q, answer), 0), actual.get((q, answer), 0)] for q, answer in keys]
    # A prefix check diagnoses a dated export; it never removes newer respondents from fitting.
    prefix = {(q, value): count for q, values in answers.items() for value, count in collections.Counter(values[:57]).items()}
    return rows, all(expected.get(k, 0)==actual.get(k, 0) for k in keys), all(expected.get(k, 0)==prefix.get(k, 0) for k in set(expected)|set(prefix))


def form_archetype(row):
    if row["age_group"] == AGE_BANDS[3]:
        return "Elderly citizen"
    if row[SPEED] <= 3.3:
        return "Mobility-limited citizen"
    if row["transit_preference"] >= .75:
        return "Transit-dependent citizen"
    if row["age_group"] == AGE_BANDS[0]:
        return "Student"
    if row["heat_tolerance"] >= .7:
        return "Outdoor worker"
    return "General pedestrian"


def build_form_population(path, counts_path, out, count, seed):
    answers = read_form(path)
    x, used = map_form(answers)
    audit, match, prefix_match = counts_audit(counts_path, answers)
    # Validation precedes final fitting. No generation or imputation uses holdout answers.
    repeats, splits = validate_form(x, seed, count)
    model = fit_normal_copula(x)
    draws = draw_normal_copula(model, count, np.random.default_rng(seed))
    rows = []
    for i, values in enumerate(draws):
        row = {"id": f"C{i+1:05d}", "age_group": AGE_BANDS[int(values[6])],
               **{k: round(float(values[j]), 6) for j, k in enumerate(FORM_VARIABLES[:6])}, "weight": 1.}
        row["archetype"] = form_archetype(row)
        rows.append(row)
    assert len({r['id'] for r in rows}) == count
    assert all(.02 <= r[k] <= .98 for r in rows for k in UNIT)
    report = ["# New walking survey: synthetic population and holdout validation", "",
              f"Observed respondents: **{len(x)}**. Final synthetic citizens: **{count}**. Seed: **{seed}**.",
              "Final export uses all respondents, after validation. Original 41-person demo outputs are unchanged.",
              "Names, emails and timestamps are excluded. Source rows are referenced only by sequential anonymous IDs.", "",
              "## Rules fixed before evaluation", "",
              "20 seeded respondent-level splits, 80/20 (ceil for holdout size). Same marginals and sample count in both models.",
              f"Diagnostic gates: {FORM_GATES}. Correlation success requires lower mean Frobenius AND max error than independent marginals.",
              "Gates are engineering diagnostics, not significance tests or evidence of behavioural validity. Repeated splits overlap; their spread is not a confidence interval.", "",
              "## Cleaning and mapping", "", "No rows dropped. Blank and 'No answer' are missing. Numeric dashes are normalised.",
              "The Q13 public-transport option with '(bus, metro, train)' is an explicit alias. Unrecognised cells stop processing with row/question only.",
              "Means use observed items only; unit scores clamp to [0.02, 0.98]. Entirely missing parameter: training median for correlation fitting only; empirical marginals use observed training values.",
              "Joint holdout tests use complete respondents only; univariate tests use observed values only.", "",
              "| Question | missing | option scores |", "|---|---:|---|"]
    for q in range(1, 17):
        labels = "; ".join(f"{label}: {value:.4g}" if np.isfinite(value) else f"{label}: missing" for label, value in FORM_OPTIONS[q].items())
        report.append(f"| Q{q} | {answers[q].count('')} | {labels} |")
    report += ["", "| Parameter | inputs | observed mean | sample SD | missing parameter |", "|---|---|---:|---:|---:|"]
    for j, k in enumerate(FORM_VARIABLES):
        desc = ", ".join(f"1 − Q{q}" if reverse else f"Q{q}" for q, reverse in FORM_ITEMS[j])
        report.append(f"| {k} | mean({desc}) | {np.nanmean(x[:,j]):.4f} | {np.nanstd(x[:,j],ddof=1):.4f} | {int(np.isnan(x[:,j]).sum())} |")
    report += ["", "Q2 speeds imply representative times 8.96, 12.5, 18.18, 23.08 minutes/km. Open-ended bands have no actual midpoint; 8.96 and 23.08 are assumptions.",
               "Q4 is already reversed in the table. Larger detours lower heat/crowd/rain tolerance; greenery detours raise preference.", "",
               "## Final population summary", "",
               "| Parameter | observed mean | synthetic mean | observed sample SD | synthetic sample SD |", "|---|---:|---:|---:|---:|"]
    for j, k in enumerate(FORM_VARIABLES[:6]):
        report.append(f"| {k} | {np.nanmean(x[:,j]):.4f} | {draws[:,j].mean():.4f} | {np.nanstd(x[:,j],ddof=1):.4f} | {draws[:,j].std(ddof=1):.4f} |")
    report += ["", "## Copula correlations and bootstrap uncertainty", "",
               "Estimator: Pearson correlation of empirical mid-rank normal scores, u=(rank−0.5)/n, z=normal inverse CDF(u). This is not identical to the Spearman sine approximation.",
               f"Positive-definite repair in final fit: {model['corrected']}. Eigenvalues below 1e-6 are clipped and the diagonal renormalised; this is a PSD repair, not an exact nearest-matrix optimisation.",
               "500 respondent bootstrap fits; pointwise percentile intervals reflect this estimator and the small sample, not causal relationships.", "",
               "| | " + " | ".join(FORM_VARIABLES) + " |", "|---|"+"---:|"*7]
    for j, k in enumerate(FORM_VARIABLES):
        report.append("| "+k+" | "+" | ".join(f"{v:.3f}" for v in model['correlation'][j])+" |")
    rng = np.random.default_rng(np.random.SeedSequence([seed, 300]))
    boot = np.array([fit_normal_copula(x[rng.integers(0, len(x), len(x))])["correlation"] for _ in range(500)])
    report += ["", "| Pair | r | 95% bootstrap interval | abs(r) >= .2 |", "|---|---:|---|---|"]
    for i in range(7):
        for j in range(i+1, 7):
            lo, hi = np.quantile(boot[:, i, j], [.025, .975])
            report.append(f"| {FORM_VARIABLES[i]} / {FORM_VARIABLES[j]} | {model['correlation'][i,j]:.3f} | [{lo:.3f}, {hi:.3f}] | {abs(model['correlation'][i,j])>=.2} |")
    report += ["", "## Repeated holdout results", "", f"Each split: {len(splits[0]['training_rows'])} train / {len(splits[0]['holdout_rows'])} unseen. Statistics: mean ± SD across 20 splits.",
               "| Parameter | model | KS | Wasserstein | signed mean difference | signed SD difference | marginal gates |", "|---|---|---:|---:|---:|---:|---|"]
    aggregates = {}
    for method in ("copula", "independent"):
        per = np.array([r[method]["per_parameter"] for r in repeats])
        joint = np.array([r[method]["joint"] for r in repeats])
        mean, sd = np.nanmean(per, axis=0), np.nanstd(per, axis=0, ddof=1)
        aggregates[method] = {"joint_mean": np.nanmean(joint, axis=0).tolist(), "joint_sd": np.nanstd(joint, axis=0, ddof=1).tolist()}
        for j, k in enumerate(FORM_VARIABLES[:6]):
            speed = j==5
            passed = bool(mean[j,0]<FORM_GATES['ks'] and np.nanmean(abs(per[:,j,2]))<=FORM_GATES['mean_speed' if speed else 'mean_unit'] and np.nanmean(abs(per[:,j,3]))<=FORM_GATES['sd_speed' if speed else 'sd_unit'])
            report.append(f"| {k} | {method} | "+" | ".join(f"{mean[j,t]:.4f} ± {sd[j,t]:.4f}" for t in range(4))+f" | {'PASS' if passed else 'FAIL'} |")
    report += ["", "Joint correlations compare empirical normal-score matrices. Pairs constant in a holdout are excluded in both models on that split.",
               f"Evaluable correlation pairs per split: {min(r['copula']['correlation_pairs_evaluable'] for r in repeats)}–{max(r['copula']['correlation_pairs_evaluable'] for r in repeats)} of 21.",
               "Mahalanobis coverage uses synthetic mean/SD and a covariance ridge 1e-6, with a 95th-percentile synthetic distance cutoff. It is a heuristic ellipsoid diagnostic.",
               "| model | max correlation error | Frobenius error | coverage | coverage gate |", "|---|---:|---:|---:|---|"]
    for method, stats in aggregates.items():
        m, s = stats['joint_mean'], stats['joint_sd']
        report.append(f"| {method} | "+" | ".join(f"{m[i]:.4f} ± {s[i]:.4f}" for i in range(3))+f" | {'PASS' if .85<=m[2]<=1 else 'FAIL'} |")
    advantage = all(aggregates['copula']['joint_mean'][j]<aggregates['independent']['joint_mean'][j] for j in (0, 1))
    report += ["", f"**Correlation baseline gate: {'PASS' if advantage else 'FAIL'}.** " + ("Copula has lower mean error on both correlation metrics." if advantage else "The copula does not outperform independence on both correlation metrics; do not claim it does."),
               f"Positive-definite repair in {sum(s['positive_definite_correction'] for s in splits)}/20 training fits.", "",
               "## Archetypes", "", "Rule order: 60+ → Elderly; speed <=3.3 → Mobility-limited; transit >=.75 → Transit-dependent; 18–24 → Student; heat tolerance >=.7 → Outdoor worker; otherwise General pedestrian.",
               "These are illustrative simulator labels. The survey does not establish student/employment/mobility status. Family / parent cannot be identified and is never assigned.", "",
               "| Archetype | count | share |", "|---|---:|---:|"]
    for label, n in sorted(collections.Counter(r['archetype'] for r in rows).items()):
        report.append(f"| {label} | {n} | {n/count:.1%} |")
    report += ["", "## Counts cross-check", "", f"Exact counts match: {match if counts_path else 'not supplied'}. First 57 rows match all provided counts: {prefix_match if counts_path else 'not tested'}.",
               "All supplied rows remain in the primary fit. The first-57 check only diagnoses the count sheet's earlier snapshot.",
               "Every expected and observed category is listed below, including missing. Delta = response CSV minus count sheet.", "",
               "| Question | Option | count sheet new | CSV | delta | observed share | synthetic option share |", "|---|---|---:|---:|---:|---:|---|"]
    for q, label, expected, actual in audit:
        synthetic_share = f"{np.mean(draws[:,6]==FORM_OPTIONS[1][label]):.1%}" if q==1 and label in FORM_OPTIONS[1] else "not identifiable*"
        report.append(f"| Q{q} | {label} | {expected} | {actual} | {actual-expected:+d} | {actual/len(x):.1%} | {synthetic_share} |")
    report += ["", "*Six composite parameters cannot be uniquely inverted into sixteen question answers. Re-discretising scores would invent answers. Synthetic age-band shares are identifiable and reported below; synthetic original-question shares require a separate question-level model.",
               "", "| Age | real share | synthetic share |", "|---|---:|---:|"]
    for age in AGE_BANDS:
        report.append(f"| {age} | {answers[1].count(age)/len(x):.1%} | {sum(r['age_group']==age for r in rows)/count:.1%} |")
    report += ["", "## Old versus new sensitivity", "", "The 39 old mapped/guessed records are available only as totals. They are excluded. Respondent-level old records were not supplied; a joint sensitivity fit cannot be computed.",
               "", "## LIMITATIONS", "", f"- n={len(x)} is small; correlation intervals are wide, especially for rare older age bands.",
               "- Self-reported stated preferences, not observed behaviour. Parameter mappings are modelling choices, not measured scales.",
               "- Questions Q5/Q6 isolate stated temperature and Q5/Q8 isolate stated crowding on shaded paths, but there is no unshaded contrast or factorial experiment. Detour choices confound time and preference. Do not claim separately measured causal effects.",
               "- Most respondents are 18–24. These citizens represent the supplied sample, not Pune's population demographics.",
               "- A thousand draws adds no independent survey evidence. Holdout checks test distributional resemblance, not simulator forecasting accuracy.",
               "- Mid-ranks for coarse ordinal ties approximate a latent Gaussian model. Interpolated quantiles can generate intermediate speeds/scores absent from the form.",
               "- At least one item can be missing: available-item averages differ in reliability. Item counts accompany every mapped respondent.",
               "- Q13's safety/transit decision is used as a rain score only as the requested heuristic. Archetype names do not establish occupation or disability.",
               "- No home/destination assignment or demo population replacement has been performed. Use assign_homes.py with --source for integration."]
    out.mkdir(parents=True, exist_ok=True)
    def write_csv(name, fields, data):
        with (out/name).open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(data)
    write_csv('synthetic_citizens.csv', ['id','archetype',*FORM_VARIABLES[:6],'weight','age_band'],
              [{**{k:v for k,v in r.items() if k!='age_group'}, 'age_band':r['age_group']} for r in rows])
    fields = ['respondent_id',*FORM_VARIABLES,*[k+'_items_used' for k in FORM_VARIABLES]]
    write_csv('participant_parameters.csv', fields, [dict(zip(fields, [f'P{i+1:03d}', *x[i], *used[i]])) for i in range(len(x))])
    write_csv('cleaned_responses.csv', ['respondent_id', *[f'Q{q}' for q in range(1,17)]],
              [{'respondent_id':f'P{i+1:03d}', **{f'Q{q}':answers[q][i] for q in range(1,17)}} for i in range(len(x))])
    source = {"participants":len(x), "method":"Gaussian copula on empirical mid-rank normal scores with empirical quantiles", "seed":seed,
              "holdout":"20 x 80/20 by respondent", "final_fit":"all supplied new-form respondents after validation",
              "response_sha256":hashlib.sha256(path.read_bytes()).hexdigest(), "counts_match":match if counts_path else None,
              "correlation_baseline_gate":advantage}
    payload = {"schema_version":1, "description":f"Synthetic citizens calibrated to {len(x)} real survey participants (Gaussian copula on normal scores). Behavioural parameters only - home/destination assigned separately. Prototype calibration, not a validated behavioural model.", "source":source, "citizens":rows}
    (out/'citizens_survey.json').write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
    (out/'validation_report.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    (out/'validation_metrics.json').write_text(json.dumps({"gates":FORM_GATES,"splits":splits,"repeats":repeats,"aggregates":aggregates},indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({"respondents":len(x),"synthetic":count,"counts_match":match,"first_57_match":prefix_match,
                      "correlation_gate":advantage,"holdout":aggregates,"output":str(out)},indent=2))


if __name__ == "__main__":
    main()
