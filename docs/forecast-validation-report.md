# Forecast Validation Report

## Scenario Catalogue

| ID | Case | Type | Expected Behaviour / Sanity Check | Automation |
| --- | --- | --- | --- | --- |
| `VAL-01` | Trailer bid with Offline, Online, and Sound work across a 4-month schedule | Realistic core scenario | Offline should land earlier, Online should peak in the middle, Sound should land later. Project rollups must sum to 100% of forecast value. Weighted totals must stay below gross totals and match dashboard pipeline views. | Added in `apps/api/tests/test_forecast_validation.py` |
| `VAL-02` | Active project with one posted actual month and then a schedule extension | Realistic core scenario | Posted actual months should stay fixed, remaining value should redistribute across the new remaining months, and no negative revenue should appear. | Added in `apps/api/tests/test_forecast_validation.py` |
| `VAL-03` | Same schedule with strong evidence versus weak evidence | Edge case | Confidence bands should widen as evidence weakens, while still bracketing the forecast median. | Added in `apps/api/tests/test_forecast_validation.py` |
| `VAL-04` | Base, upside, and downside scenario outputs for a bid project | Realistic core scenario | `downside < base < upside` for projected total revenue and weighted revenue. Downside timing should move later when schedule-slip assumptions are applied. | Added in `apps/api/tests/test_forecast_validation.py` |
| `VAL-05` | Promotion of a slipped downside scenario into the forecast engine | Failure-pattern case | Promotion should preserve the commercial meaning of the scenario. If the promoted forecast still carries earlier schedule months than the scenario, flag it as misleading. | Added in `apps/api/tests/test_forecast_validation.py` |
| `VAL-06` | Posted actuals already exceed quoted value | Edge case / failure-pattern case | Future forecast months should not go negative, but the system should treat this as an overburn situation needing explicit operator attention. | Added in `apps/api/tests/test_forecast_validation.py` |
| `VAL-07` | Sparse comparable history or missing target calendar | Failure-pattern case | Predictive monthly spread should stay empty and surface a missing-history or missing-calendar signal rather than inventing a precise monthly curve. | Existing coverage in `apps/api/tests/test_predictions.py` |
| `VAL-08` | Portfolio/dashboard rollups on filtered operational views | Realistic core scenario | Dashboard monthly and pipeline rollups should reconcile with the persisted forecast version and should not double count value. | Added in `apps/api/tests/test_forecast_validation.py` plus existing dashboard tests |

## Automated Tests Added

- `test_validation_core_post_scenario_matches_timing_weighting_and_dashboard_rollups`
- `test_validation_reforecast_keeps_posted_actuals_and_redistributes_remaining_work`
- `test_validation_confidence_bands_widen_when_evidence_is_weaker`
- `test_validation_prediction_scenarios_order_outputs_but_flag_lost_schedule_shift_on_promotion`
- `test_validation_edge_case_overburn_actuals_need_operator_attention`

## Suspicious Output Flags

| Flag | Meaning | Why It Matters Commercially |
| --- | --- | --- |
| `scenario_schedule_shift_not_reflected_in_forecast` | The predictive scenario says revenue slips later, but the promoted forecast still retains earlier schedule months. | Users can believe downside timing risk is in the forecast when the cash curve is still anchored to the original schedule. |
| `actuals_exceed_quote_without_explicit_overburn_flag` | Posted revenue already exceeds the quoted value, but the forecast only rolls forward numerically without a clear overburn warning. | Finance or account leads may miss that the job is already above quote and treat it as a normal reforecast. |
| `high_confidence_without_monthly_history` | Confidence reads high despite little or no usable month-profile evidence. | A forecast can look more certain than the underlying evidence justifies. This flag is recommended even though it is not yet emitted automatically. |
| `uniform_scenario_multiplier_hides_discipline_specific_risk` | Scenario movement is applied broadly rather than by discipline behaviour. | Real post projects often slip unevenly; a uniform downside can understate where margin or timing risk actually sits. |

## Weak Spots In Current Logic

- Scenario promotion does not fully preserve timing-slip assumptions when project discipline schedules already exist. The forecast engine resolves months from project schedules before it falls back to predictive monthly scenario months, so a slipped downside scenario can still leave early revenue in the promoted forecast.
- Confidence bands are commercially directional but not calibrated. The current low/high ranges widen correctly with weaker evidence, but they are generated from heuristic percentages or curve ratios rather than measured monthly error by discipline, stage, or profile.
- Scenario changes are structurally broad-brush. Quote, actual, and probability multipliers are applied uniformly across disciplines and months, which is explainable but too coarse for many real post jobs where editorial, online, grade, and sound move differently.
- Pipeline weighting is internally consistent, but it is version-level only. The same probability is applied across every month and discipline of the version, which can understate how much late-stage booked milestones behave differently from early speculative months.
- Partial actual assimilation is numerically sensible, but it lacks stronger exception handling. When actuals outrun quote, the engine correctly stops future negative revenue, yet it does not add a first-class “overburn” or “already above quote” signal.
- Sparse-evidence fallback can still look more precise than it is. When predictive monthly history is thin, the engine falls back to deterministic discipline curve shapes, which keeps the system operational but can visually imply stronger timing evidence than the project actually has.

## Validation Summary

- The current engine is commercially plausible for straightforward post schedules, partial actual reforecasting, dashboard rollups, and basic pipeline-weighted reporting.
- The main credibility risks are around promoted scenario timing, overburn visibility, and the degree of confidence implied by heuristic ranges.
- The numbers are technically coherent and often operationally useful, but they should not yet be treated as fully reliable for cash timing stress cases without operator review.
