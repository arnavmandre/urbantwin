# Phase 10 — survey-calibrated synthetic citizens

Turns **41 real survey responses** into a synthetic population the simulator can
run, preserving the population-level pattern instead of cloning individuals.

```
Survey DATA (1).xlsx           41 respondents x 4 scenarios = 164 observations
        |  ingest_survey.py
   data/*.csv                  participants / scenarios / responses / joined
        |  fit_behaviour.py
   participant_parameters.csv  6 simulator parameters per real participant
        |  generate_citizens.py        Gaussian copula
   synthetic_citizens.csv      1,000 citizens preserving the joint distribution
        |  assign_homes.py
   Simulation/citizens_survey_city_osm.json
        |
   cd Simulation; python main.py citizens_survey_city_osm.json city_osm.json
```

## Run it

### October 2026 Q1–Q16 walking form

The existing generator also accepts the new respondent-level form. It writes to
`phase10/data/new_survey/`, leaving the 41-person demo population in place:

```powershell
python phase10/generate_citizens.py "path/to/Form responses 1.csv" `
  --option-counts "path/to/Option counts.csv" --count 1000 --seed 7
python -m unittest phase10.test_generate_citizens
```

Dependencies for this mode are NumPy and SciPy (the CSV parser is standard library).
`cleaned_responses.csv` excludes names, emails and timestamps and can be supplied
back as the response input to reproduce the results. The source checksum will
then reflect that anonymised input. Each real respondent has a sequential ID.

The run creates `synthetic_citizens.csv`, `citizens_survey.json`, mapped parameters
with item counts, `validation_report.md` and machine-readable holdout metrics/splits.
Read the validation report before replacing a demo population. Its gates are
diagnostic checks, not evidence of predictive or causal validity.

On the supplied export: 63 new respondents; the counts sheet matches the first
57 exactly. Twenty 50/13 splits fit mid-rank normal-score copulas and independent
marginals on training respondents only. The copula does **not** outperform
independence on both correlation errors, and coverage is 84.9% against the preset
85% lower bound. All six mean marginal gates pass for the copula. The final
1,000 draws use all 63 respondents after evaluation. The 39 old mapped/guessed
records are excluded because only their totals were supplied.

To place these citizens on London's city for a separate simulator test:

```powershell
python phase10/assign_homes.py --city city_osm.json `
  --source phase10/data/new_survey/citizens_survey.json `
  --out phase10/data/new_survey/citizens_ready.json
python Simulation/main.py phase10/data/new_survey/citizens_ready.json `
  Simulation/city_osm.json --output phase10/data/new_survey/simulation_smoke.json
```

Archetypes are heuristic display labels, not measured occupations or disabilities.
The six composite scores cannot reconstruct the sixteen original question answers.
The report marks those synthetic question shares as unidentifiable rather than
inventing them. Old-per-respondent sensitivity analysis needs the old raw rows.

### Original 41-person survey

```powershell
python phase10\ingest_survey.py
python phase10\fit_behaviour.py
python phase10\generate_citizens.py --count 1000 --seed 7
python phase10\assign_homes.py
python phase10\validate_survey.py
```

## Random Forest behavior benchmark

Install once and train:

```powershell
python -m pip install -r phase10\requirements.txt
python -u phase10\train_random_forest.py 2>&1 | Tee-Object phase10\training.log
```

The trainer prevents participant leakage, runs five-fold grouped cross-validation,
keeps eight participants untouched for a final test, compares against simple and
shuffled-label baselines, and writes deployable artifacts plus
`models/model_card.json` and `models/MODEL_REPORT.md`. A target marked
`not_validated` must not drive claims or replace the transparent simulator rule.

Deterministic: same seed, same population.

## Where each parameter comes from

Three are **direct measurements**. Three are **derived**.

| Simulator parameter | Source | Kind |
|---|---|---|
| `walking_speed_kmh` | Q5 self-reported minutes per km, band midpoint | direct |
| `green_preference` | Q8 green-space influence (1–5), nudged by Q13 route choice | direct |
| `transit_preference` | Q4 public-transport frequency | direct |
| `heat_tolerance` | Q3 self-rated heat sensitivity + comfort collapse S01→S03, attributed via Q19 | derived |
| `crowd_tolerance` | S02 stress + comfort collapse + Q13 route trade-off | derived |
| `rain_tolerance` | Q18 avoidance in the rain scenario, attributed via Q19 | derived |

## The limitation that matters

**Scenarios S01 → S02 → S03 raise temperature *and* crowding while lowering
shade, all at once.** A comfort drop across them cannot by itself be attributed
to any one of the three — the design is confounded.

Two things partially rescue it:

- **Q3** measures heat sensitivity independently of any scenario.
- **Q19** asks which single factor would most drive avoidance, attributing each
  person's compound reaction to a named cause (Heavy rainfall 13, Extreme heat
  12, Crowding 6, Lack of shelter 5).

So the compound slope is shared across the three axes, weighted toward whichever
factor that participant named. That is honest inference from a confounded
design, **not** clean per-factor measurement. Two decorrelating scenarios
(hot-but-empty, cool-but-crowded) would fix it properly and cost ~90 seconds
more per respondent.

Also: **S04 carries no comfort or stress rating**, only avoidance. Rain
sensitivity is therefore identified from one avoidance question, which is a
thinner signal than heat or crowd.

## Why a copula, not independent sampling

Sampling each parameter independently would manufacture citizens who are
heat-sensitive *and* crowd-loving *and* fast-walking — combinations nobody in
the sample exhibited. The copula keeps the observed covariance.

Real relationships found in the data, and preserved:

| relationship | real | synthetic |
|---|---|---|
| crowd tolerance vs green preference | −0.46 | −0.39 |
| heat tolerance vs crowd tolerance | +0.43 | +0.35 |
| heat tolerance vs green preference | −0.30 | −0.17 |

People who suffer in heat care more about trees. That is a finding from the
survey, not an assumption, and it survives into the synthetic population.

## Validation

`validate_survey.py` checks three things, in increasing order of what they prove:

1. **Marginals** — every parameter's mean within 0.013 of the real sample
2. **Structure** — worst correlation drift 0.14 across all 15 pairs
3. **Holdout** — a fresh copula is fitted on 36 participants only, then five
   unseen participants are checked against its predictive 95% ranges. This is
   a distributional sanity check, not proof of individual behavior prediction.

"Matches the data we fitted on" is circular. The holdout is the part that counts.

## Honest framing

**Say:**
- "Behavioural parameters are calibrated from 41 real participants."
- "We sample a synthetic population that preserves the observed joint
  distribution, validated against held-out participants."
- "A prototype behavioural calibration, not a validated behavioural model."

**Do not say:**
- "Our model predicts pedestrian behaviour." 41 people, self-reported intention,
  no ground-truth behaviour.
- "We separately measured heat, crowd and rain sensitivity." The scenario design
  is confounded; see above.
- "Home and destination come from the survey." They do not —
  `assign_homes.py` is a documented trip-distribution heuristic.

## Notes on the collected data

- **8 of 41 respondents are under 18.** Worth knowing before this dataset is
  published or reused.
- One free-text answer discloses a disability and asks for accessible spaces.
  Accessibility was deliberately removed from the simulator's model, so that
  response is recorded in the dataset but has no parameter to drive. Worth a
  sentence in the write-up rather than silent omission.
- The only identifying column in the export was the form Timestamp, which is
  dropped at ingest. Participants are P001–P041 in submission order.
