# October 2026 walking survey

This package contains 1,000 synthetic citizens calibrated to the 63 supplied
respondents. Names, emails and timestamps are excluded from every output.

Read `validation_report.md` first. The copula passed the six marginal diagnostic
gates, but failed the comparison against independent marginals and its coverage
gate. This population is exploratory and has not replaced the demo's citizens.

## Reproduce

From the package root, with Python, NumPy and SciPy installed:

```powershell
python -m pip install numpy scipy
python phase10/generate_citizens.py phase10/data/new_survey/cleaned_responses.csv `
  --option-counts phase10/data/new_survey/option_counts.csv --count 1000 --seed 7
```

The anonymised input reproduces the population, holdout metrics and report exactly.
The input-file checksum changes because the original private file included names
and emails. Age codes in `participant_parameters.csv` are 0=18–24, 1=25–34,
2=35–59, 3=60 or above; all other mappings are in the validation report.

The output JSON contains behaviour only; home/destination assignment is a separate
heuristic. The active Pune demo retains 600 agents by default from the 41-person
calibration. This 63-response experiment failed joint holdout checks and the
coverage gate and is not its replacement population.

## Files

- `phase10/generate_citizens.py`: the existing generator extended for this new form.
- `citizens_survey.json`: behavioural profiles in the simulator's JSON envelope.
- `synthetic_citizens.csv`: the same profiles plus age band.
- `cleaned_responses.csv`: anonymised Q1–Q16 rows, with blanks preserved.
- `participant_parameters.csv`: mapped scores and observed item counts per respondent.
- `option_counts.csv`: the aggregate control totals supplied by the user.
- `validation_report.md`: mappings, 500-bootstrap correlation intervals, 20 holdouts,
  independent baseline, diagnostic verdicts and limitations.
- `validation_metrics.json`: each respondent split and each measured validation result.

The counts sheet matches the first 57 respondents exactly. The final population
uses all 63. The 39 old mapped/guessed records are excluded. Their respondent-level
rows were not supplied, so old-versus-new joint sensitivity cannot be computed.

Six composite scores cannot be inverted into sixteen individual question answers.
The report therefore provides synthetic age shares and marks the other synthetic
question shares as unidentifiable.
