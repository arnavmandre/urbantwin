# New walking survey: synthetic population and holdout validation

Observed respondents: **63**. Final synthetic citizens: **1000**. Seed: **7**.
Final export uses all respondents, after validation. Original 41-person demo outputs are unchanged.
Names, emails and timestamps are excluded. Source rows are referenced only by sequential anonymous IDs.

## Rules fixed before evaluation

20 seeded respondent-level splits, 80/20 (ceil for holdout size). Same marginals and sample count in both models.
Diagnostic gates: {'ks': 0.25, 'mean_unit': 0.12, 'sd_unit': 0.12, 'mean_speed': 0.8, 'sd_speed': 0.8, 'coverage_low': 0.85, 'coverage_high': 1.0}. Correlation success requires lower mean Frobenius AND max error than independent marginals.
Gates are engineering diagnostics, not significance tests or evidence of behavioural validity. Repeated splits overlap; their spread is not a confidence interval.

## Cleaning and mapping

No rows dropped. Blank and 'No answer' are missing. Numeric dashes are normalised.
The Q13 public-transport option with '(bus, metro, train)' is an explicit alias. Unrecognised cells stop processing with row/question only.
Means use observed items only; unit scores clamp to [0.02, 0.98]. Entirely missing parameter: training median for correlation fitting only; empirical marginals use observed training values.
Joint holdout tests use complete respondents only; univariate tests use observed values only.

| Question | missing | option scores |
|---|---:|---|
| Q1 | 0 | 18–24: 0; 25–34: 1; 35–59: 2; 60 or above: 3 |
| Q2 | 0 | Under 10 minutes: 6.7; 10–15 minutes: 4.8; 16–20 minutes: 3.3; Over 20 minutes: 2.6 |
| Q3 | 1 | Almost daily: 1; Weekly: 0.6667; Monthly: 0.3333; Rarely or never: 0 |
| Q4 | 0 | Not at all: 1; A little: 0.6667; Quite a bit: 0.3333; A lot: 0 |
| Q5 | 0 | Very uncomfortable: 0; Slightly uncomfortable: 0.3333; Comfortable: 0.6667; Very comfortable: 1 |
| Q6 | 0 | Very uncomfortable: 0; Slightly uncomfortable: 0.3333; Comfortable: 0.6667; Very comfortable: 1 |
| Q7 | 0 | No extra time: 0; Up to 5 minutes: 0.3333; 6–10 minutes: 0.6667; More than 10 minutes: 1 |
| Q8 | 1 | Very uncomfortable: 0; Slightly uncomfortable: 0.3333; Comfortable: 0.6667; Very comfortable: 1 |
| Q9 | 0 | No extra time: 0; Up to 5 minutes: 0.3333; 6–10 minutes: 0.6667; More than 10 minutes: 1 |
| Q10 | 1 | Definitely would not: 0; Probably would not: 0.3333; Probably would: 0.6667; Definitely would: 1 |
| Q11 | 1 | Definitely would not: 0; Probably would not: 0.3333; Probably would: 0.6667; Definitely would: 1 |
| Q12 | 1 | No extra time: 0; Up to 5 minutes: 0.3333; 6–10 minutes: 0.6667; More than 10 minutes: 1 |
| Q13 | 2 | Take the dry route: 1; Use available public transport: 0.6667; Wait somewhere safe: 0.3333; Delay or cancel the trip: 0 |
| Q14 | 1 | A 15-minute route with trees and gardens: 1; A 10-minute route with little greenery: 0; Either route is fine: 0.5; I would avoid walking: missing |
| Q15 | 1 | No extra time: 0; Up to 5 minutes: 0.3333; 6–10 minutes: 0.6667; More than 10 minutes: 1 |
| Q16 | 1 | Definitely would not: 0; Probably would not: 0.3333; Probably would: 0.6667; Definitely would: 1 |

| Parameter | inputs | observed mean | sample SD | missing parameter |
|---|---|---:|---:|---:|
| heat_tolerance | mean(Q4, Q5, Q6, 1 − Q7) | 0.4987 | 0.1643 | 0 |
| rain_tolerance | mean(Q10, Q11, 1 − Q12, Q13) | 0.6130 | 0.2016 | 1 |
| crowd_tolerance | mean(Q8, 1 − Q9) | 0.5159 | 0.1940 | 0 |
| green_preference | mean(Q14, Q15) | 0.5114 | 0.3194 | 1 |
| transit_preference | mean(Q3, Q16) | 0.3998 | 0.2397 | 0 |
| walking_speed_kmh | mean(Q2) | 5.6841 | 1.2043 | 0 |
| age_band | mean(Q1) | 0.5079 | 0.9136 | 0 |

Q2 speeds imply representative times 8.96, 12.5, 18.18, 23.08 minutes/km. Open-ended bands have no actual midpoint; 8.96 and 23.08 are assumptions.
Q4 is already reversed in the table. Larger detours lower heat/crowd/rain tolerance; greenery detours raise preference.

## Final population summary

| Parameter | observed mean | synthetic mean | observed sample SD | synthetic sample SD |
|---|---:|---:|---:|---:|
| heat_tolerance | 0.4987 | 0.4967 | 0.1643 | 0.1563 |
| rain_tolerance | 0.6130 | 0.6097 | 0.2016 | 0.1882 |
| crowd_tolerance | 0.5159 | 0.5183 | 0.1940 | 0.1841 |
| green_preference | 0.5114 | 0.5005 | 0.3194 | 0.3117 |
| transit_preference | 0.3998 | 0.4092 | 0.2397 | 0.2331 |
| walking_speed_kmh | 5.6841 | 5.7065 | 1.2043 | 1.1462 |

## Copula correlations and bootstrap uncertainty

Estimator: Pearson correlation of empirical mid-rank normal scores, u=(rank−0.5)/n, z=normal inverse CDF(u). This is not identical to the Spearman sine approximation.
Positive-definite repair in final fit: False. Eigenvalues below 1e-6 are clipped and the diagonal renormalised; this is a PSD repair, not an exact nearest-matrix optimisation.
500 respondent bootstrap fits; pointwise percentile intervals reflect this estimator and the small sample, not causal relationships.

| | heat_tolerance | rain_tolerance | crowd_tolerance | green_preference | transit_preference | walking_speed_kmh | age_band |
|---|---:|---:|---:|---:|---:|---:|---:|
| heat_tolerance | 1.000 | 0.201 | 0.080 | -0.250 | 0.051 | 0.108 | -0.033 |
| rain_tolerance | 0.201 | 1.000 | 0.061 | -0.053 | -0.081 | 0.028 | 0.019 |
| crowd_tolerance | 0.080 | 0.061 | 1.000 | -0.110 | -0.031 | 0.075 | -0.156 |
| green_preference | -0.250 | -0.053 | -0.110 | 1.000 | -0.116 | -0.127 | 0.258 |
| transit_preference | 0.051 | -0.081 | -0.031 | -0.116 | 1.000 | 0.130 | -0.149 |
| walking_speed_kmh | 0.108 | 0.028 | 0.075 | -0.127 | 0.130 | 1.000 | -0.488 |
| age_band | -0.033 | 0.019 | -0.156 | 0.258 | -0.149 | -0.488 | 1.000 |

| Pair | r | 95% bootstrap interval | abs(r) >= .2 |
|---|---:|---|---|
| heat_tolerance / rain_tolerance | 0.201 | [-0.008, 0.384] | True |
| heat_tolerance / crowd_tolerance | 0.080 | [-0.158, 0.384] | False |
| heat_tolerance / green_preference | -0.250 | [-0.463, 0.013] | True |
| heat_tolerance / transit_preference | 0.051 | [-0.193, 0.277] | False |
| heat_tolerance / walking_speed_kmh | 0.108 | [-0.103, 0.300] | False |
| heat_tolerance / age_band | -0.033 | [-0.222, 0.183] | False |
| rain_tolerance / crowd_tolerance | 0.061 | [-0.156, 0.273] | False |
| rain_tolerance / green_preference | -0.053 | [-0.323, 0.223] | False |
| rain_tolerance / transit_preference | -0.081 | [-0.310, 0.184] | False |
| rain_tolerance / walking_speed_kmh | 0.028 | [-0.272, 0.296] | False |
| rain_tolerance / age_band | 0.019 | [-0.253, 0.292] | False |
| crowd_tolerance / green_preference | -0.110 | [-0.347, 0.109] | False |
| crowd_tolerance / transit_preference | -0.031 | [-0.264, 0.261] | False |
| crowd_tolerance / walking_speed_kmh | 0.075 | [-0.134, 0.275] | False |
| crowd_tolerance / age_band | -0.156 | [-0.336, 0.006] | False |
| green_preference / transit_preference | -0.116 | [-0.330, 0.091] | False |
| green_preference / walking_speed_kmh | -0.127 | [-0.344, 0.148] | False |
| green_preference / age_band | 0.258 | [-0.010, 0.470] | True |
| transit_preference / walking_speed_kmh | 0.130 | [-0.109, 0.346] | False |
| transit_preference / age_band | -0.149 | [-0.372, 0.090] | False |
| walking_speed_kmh / age_band | -0.488 | [-0.695, -0.247] | True |

## Repeated holdout results

Each split: 50 train / 13 unseen. Statistics: mean ± SD across 20 splits.
| Parameter | model | KS | Wasserstein | signed mean difference | signed SD difference | marginal gates |
|---|---|---:|---:|---:|---:|---|
| heat_tolerance | copula | 0.2030 ± 0.0823 | 0.0579 ± 0.0155 | 0.0041 ± 0.0441 | -0.0087 ± 0.0248 | PASS |
| rain_tolerance | copula | 0.2398 ± 0.0521 | 0.0775 ± 0.0191 | -0.0037 ± 0.0596 | -0.0168 ± 0.0620 | PASS |
| crowd_tolerance | copula | 0.1972 ± 0.0871 | 0.0700 ± 0.0332 | -0.0119 ± 0.0652 | -0.0112 ± 0.0372 | PASS |
| green_preference | copula | 0.2479 ± 0.0625 | 0.1188 ± 0.0442 | -0.0022 ± 0.1114 | -0.0002 ± 0.0620 | PASS |
| transit_preference | copula | 0.2142 ± 0.0914 | 0.0800 ± 0.0295 | 0.0132 ± 0.0600 | 0.0258 ± 0.0447 | PASS |
| walking_speed_kmh | copula | 0.1511 ± 0.0756 | 0.3538 ± 0.1713 | 0.0148 ± 0.3675 | -0.0330 ± 0.2553 | PASS |
| heat_tolerance | independent | 0.2034 ± 0.0838 | 0.0586 ± 0.0171 | 0.0076 ± 0.0451 | -0.0075 ± 0.0262 | PASS |
| rain_tolerance | independent | 0.2409 ± 0.0485 | 0.0779 ± 0.0174 | -0.0037 ± 0.0608 | -0.0159 ± 0.0610 | PASS |
| crowd_tolerance | independent | 0.2025 ± 0.0912 | 0.0702 ± 0.0342 | -0.0112 ± 0.0666 | -0.0101 ± 0.0373 | PASS |
| green_preference | independent | 0.2526 ± 0.0611 | 0.1222 ± 0.0460 | -0.0049 ± 0.1165 | -0.0009 ± 0.0625 | FAIL |
| transit_preference | independent | 0.2177 ± 0.0925 | 0.0807 ± 0.0298 | 0.0156 ± 0.0600 | 0.0269 ± 0.0456 | PASS |
| walking_speed_kmh | independent | 0.1472 ± 0.0771 | 0.3507 ± 0.1747 | 0.0337 ± 0.3548 | -0.0440 ± 0.2492 | PASS |

Joint correlations compare empirical normal-score matrices. Pairs constant in a holdout are excluded in both models on that split.
Evaluable correlation pairs per split: 21–21 of 21.
Mahalanobis coverage uses synthetic mean/SD and a covariance ridge 1e-6, with a 95th-percentile synthetic distance cutoff. It is a heuristic ellipsoid diagnostic.
| model | max correlation error | Frobenius error | coverage | coverage gate |
|---|---:|---:|---:|---|
| copula | 0.6755 ± 0.1106 | 2.0725 ± 0.2928 | 0.8487 ± 0.1162 | FAIL |
| independent | 0.6774 ± 0.1067 | 2.0257 ± 0.2996 | 0.8917 ± 0.1206 | PASS |

**Correlation baseline gate: FAIL.** The copula does not outperform independence on both correlation metrics; do not claim it does.
Positive-definite repair in 0/20 training fits.

## Archetypes

Rule order: 60+ → Elderly; speed <=3.3 → Mobility-limited; transit >=.75 → Transit-dependent; 18–24 → Student; heat tolerance >=.7 → Outdoor worker; otherwise General pedestrian.
These are illustrative simulator labels. The survey does not establish student/employment/mobility status. Family / parent cannot be identified and is never assigned.

| Archetype | count | share |
|---|---:|---:|
| Elderly citizen | 26 | 2.6% |
| General pedestrian | 151 | 15.1% |
| Mobility-limited citizen | 50 | 5.0% |
| Outdoor worker | 27 | 2.7% |
| Student | 671 | 67.1% |
| Transit-dependent citizen | 75 | 7.5% |

## Counts cross-check

Exact counts match: False. First 57 rows match all provided counts: True.
All supplied rows remain in the primary fit. The first-57 check only diagnoses the count sheet's earlier snapshot.
Every expected and observed category is listed below, including missing. Delta = response CSV minus count sheet.

| Question | Option | count sheet new | CSV | delta | observed share | synthetic option share |
|---|---|---:|---:|---:|---:|---|
| Q1 | 18–24 | 42 | 47 | +5 | 74.6% | 75.5% |
| Q1 | 25–34 | 2 | 2 | +0 | 3.2% | 3.8% |
| Q1 | 35–59 | 11 | 12 | +1 | 19.0% | 18.1% |
| Q1 | 60 or above | 2 | 2 | +0 | 3.2% | 2.6% |
| Q2 | 10–15 minutes | 23 | 24 | +1 | 38.1% | not identifiable* |
| Q2 | 16–20 minutes | 3 | 3 | +0 | 4.8% | not identifiable* |
| Q2 | Over 20 minutes | 2 | 2 | +0 | 3.2% | not identifiable* |
| Q2 | Under 10 minutes | 29 | 34 | +5 | 54.0% | not identifiable* |
| Q3 | No answer | 1 | 1 | +0 | 1.6% | not identifiable* |
| Q3 | Almost daily | 10 | 10 | +0 | 15.9% | not identifiable* |
| Q3 | Monthly | 12 | 13 | +1 | 20.6% | not identifiable* |
| Q3 | Rarely or never | 24 | 29 | +5 | 46.0% | not identifiable* |
| Q3 | Weekly | 10 | 10 | +0 | 15.9% | not identifiable* |
| Q4 | A little | 15 | 17 | +2 | 27.0% | not identifiable* |
| Q4 | A lot | 14 | 15 | +1 | 23.8% | not identifiable* |
| Q4 | Not at all | 2 | 2 | +0 | 3.2% | not identifiable* |
| Q4 | Quite a bit | 26 | 29 | +3 | 46.0% | not identifiable* |
| Q5 | Comfortable | 31 | 35 | +4 | 55.6% | not identifiable* |
| Q5 | Slightly uncomfortable | 8 | 9 | +1 | 14.3% | not identifiable* |
| Q5 | Very comfortable | 15 | 16 | +1 | 25.4% | not identifiable* |
| Q5 | Very uncomfortable | 3 | 3 | +0 | 4.8% | not identifiable* |
| Q6 | Comfortable | 12 | 13 | +1 | 20.6% | not identifiable* |
| Q6 | Slightly uncomfortable | 26 | 29 | +3 | 46.0% | not identifiable* |
| Q6 | Very comfortable | 4 | 4 | +0 | 6.3% | not identifiable* |
| Q6 | Very uncomfortable | 15 | 17 | +2 | 27.0% | not identifiable* |
| Q7 | 6–10 minutes | 11 | 14 | +3 | 22.2% | not identifiable* |
| Q7 | More than 10 minutes | 5 | 5 | +0 | 7.9% | not identifiable* |
| Q7 | No extra time | 12 | 12 | +0 | 19.0% | not identifiable* |
| Q7 | Up to 5 minutes | 29 | 32 | +3 | 50.8% | not identifiable* |
| Q8 | No answer | 1 | 1 | +0 | 1.6% | not identifiable* |
| Q8 | Comfortable | 21 | 23 | +2 | 36.5% | not identifiable* |
| Q8 | Slightly uncomfortable | 25 | 28 | +3 | 44.4% | not identifiable* |
| Q8 | Very comfortable | 2 | 2 | +0 | 3.2% | not identifiable* |
| Q8 | Very uncomfortable | 8 | 9 | +1 | 14.3% | not identifiable* |
| Q9 | 6–10 minutes | 13 | 14 | +1 | 22.2% | not identifiable* |
| Q9 | More than 10 minutes | 5 | 5 | +0 | 7.9% | not identifiable* |
| Q9 | No extra time | 10 | 10 | +0 | 15.9% | not identifiable* |
| Q9 | Up to 5 minutes | 29 | 34 | +5 | 54.0% | not identifiable* |
| Q10 | No answer | 1 | 1 | +0 | 1.6% | not identifiable* |
| Q10 | Definitely would | 22 | 27 | +5 | 42.9% | not identifiable* |
| Q10 | Definitely would not | 4 | 4 | +0 | 6.3% | not identifiable* |
| Q10 | Probably would | 22 | 23 | +1 | 36.5% | not identifiable* |
| Q10 | Probably would not | 8 | 8 | +0 | 12.7% | not identifiable* |
| Q11 | No answer | 1 | 1 | +0 | 1.6% | not identifiable* |
| Q11 | Definitely would | 6 | 9 | +3 | 14.3% | not identifiable* |
| Q11 | Definitely would not | 14 | 15 | +1 | 23.8% | not identifiable* |
| Q11 | Probably would | 16 | 17 | +1 | 27.0% | not identifiable* |
| Q11 | Probably would not | 20 | 21 | +1 | 33.3% | not identifiable* |
| Q12 | No answer | 1 | 1 | +0 | 1.6% | not identifiable* |
| Q12 | 6–10 minutes | 21 | 22 | +1 | 34.9% | not identifiable* |
| Q12 | More than 10 minutes | 10 | 11 | +1 | 17.5% | not identifiable* |
| Q12 | No extra time | 7 | 8 | +1 | 12.7% | not identifiable* |
| Q12 | Up to 5 minutes | 18 | 21 | +3 | 33.3% | not identifiable* |
| Q13 | No answer | 2 | 2 | +0 | 3.2% | not identifiable* |
| Q13 | Delay or cancel the trip | 4 | 4 | +0 | 6.3% | not identifiable* |
| Q13 | Take the dry route | 40 | 44 | +4 | 69.8% | not identifiable* |
| Q13 | Use available public transport | 5 | 5 | +0 | 7.9% | not identifiable* |
| Q13 | Wait somewhere safe | 6 | 8 | +2 | 12.7% | not identifiable* |
| Q14 | No answer | 1 | 1 | +0 | 1.6% | not identifiable* |
| Q14 | A 10-minute route with little greenery | 12 | 13 | +1 | 20.6% | not identifiable* |
| Q14 | A 15-minute route with trees and gardens | 26 | 29 | +3 | 46.0% | not identifiable* |
| Q14 | Either route is fine | 14 | 16 | +2 | 25.4% | not identifiable* |
| Q14 | I would avoid walking | 4 | 4 | +0 | 6.3% | not identifiable* |
| Q15 | No answer | 1 | 1 | +0 | 1.6% | not identifiable* |
| Q15 | 6–10 minutes | 10 | 12 | +2 | 19.0% | not identifiable* |
| Q15 | More than 10 minutes | 8 | 9 | +1 | 14.3% | not identifiable* |
| Q15 | No extra time | 16 | 17 | +1 | 27.0% | not identifiable* |
| Q15 | Up to 5 minutes | 22 | 24 | +2 | 38.1% | not identifiable* |
| Q16 | No answer | 1 | 1 | +0 | 1.6% | not identifiable* |
| Q16 | Definitely would | 12 | 12 | +0 | 19.0% | not identifiable* |
| Q16 | Definitely would not | 14 | 15 | +1 | 23.8% | not identifiable* |
| Q16 | Probably would | 13 | 16 | +3 | 25.4% | not identifiable* |
| Q16 | Probably would not | 17 | 19 | +2 | 30.2% | not identifiable* |

*Six composite parameters cannot be uniquely inverted into sixteen question answers. Re-discretising scores would invent answers. Synthetic age-band shares are identifiable and reported below; synthetic original-question shares require a separate question-level model.

| Age | real share | synthetic share |
|---|---:|---:|
| 18–24 | 74.6% | 75.5% |
| 25–34 | 3.2% | 3.8% |
| 35–59 | 19.0% | 18.1% |
| 60 or above | 3.2% | 2.6% |

## Old versus new sensitivity

The 39 old mapped/guessed records are available only as totals. They are excluded. Respondent-level old records were not supplied; a joint sensitivity fit cannot be computed.

## LIMITATIONS

- n=63 is small; correlation intervals are wide, especially for rare older age bands.
- Self-reported stated preferences, not observed behaviour. Parameter mappings are modelling choices, not measured scales.
- Questions Q5/Q6 isolate stated temperature and Q5/Q8 isolate stated crowding on shaded paths, but there is no unshaded contrast or factorial experiment. Detour choices confound time and preference. Do not claim separately measured causal effects.
- Most respondents are 18–24. These citizens represent the supplied sample, not Pune's population demographics.
- A thousand draws adds no independent survey evidence. Holdout checks test distributional resemblance, not simulator forecasting accuracy.
- Mid-ranks for coarse ordinal ties approximate a latent Gaussian model. Interpolated quantiles can generate intermediate speeds/scores absent from the form.
- At least one item can be missing: available-item averages differ in reliability. Item counts accompany every mapped respondent.
- Q13's safety/transit decision is used as a rain score only as the requested heuristic. Archetype names do not establish occupation or disability.
- No home/destination assignment or demo population replacement has been performed. Use assign_homes.py with --source for integration.
