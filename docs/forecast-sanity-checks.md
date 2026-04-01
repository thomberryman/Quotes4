# Forecast Sanity Checks

## Rules

| Rule key | Severity | Implemented | Purpose |
| --- | --- | --- | --- |
| `revenue_before_project_start` | `warning` | Yes | Detect forecast revenue landing before the current project start month. |
| `delivery_before_upstream` | `warning` | Yes | Detect mastering/delivery revenue starting before upstream finishing disciplines begin. |
| `flat_curve_on_shaped_project` | `warning` | Yes | Detect fully linear or even spreads on work that should show shaped timing. |
| `confidence_too_high_for_metadata` | `warning` | Yes | Detect high confidence when project metadata completeness is low. |
| `narrow_bands_sparse_data` | `warning` | Yes | Detect unusually narrow forecast ranges when data sufficiency is weak. |
| `scenario_outputs_too_similar` | `warning` | Yes | Detect scenario versions that are too close together to be decision-useful. |
| `project_total_mismatch_line_total` | `error` | Yes | Detect project totals that do not reconcile to line totals. |
| `project_total_mismatch_discipline_total` | `error` | Yes | Detect project totals that do not reconcile to discipline rollups. |
| `rollup_total_mismatch` | `error` | Yes | Detect project rollups that do not reconcile to project totals. |
| `actuals_not_assimilated` | `error` | Yes | Detect posted actual months missing from discipline forecast rows. |
| `actuals_not_replacing_forecast` | `error` | Yes | Detect posted actuals not replacing forecast values on completed work. |
| `project_actuals_not_reflected` | `error` | Yes | Detect project-level rollups that do not reflect posted actual coverage. |
| `lost_opportunity_weighted_value` | `error` | Yes | Detect lost work still contributing weighted forecast value. |
| `no_delta_after_schedule_shift` | `warning` | Yes | Detect schedule windows that changed materially without forecast month deltas. |
| `underquote_vs_comparable_history` | `warning` | Yes | Detect obvious underquote/overrun risk from persisted predictive evidence. |
| `fallback_tier_missing` | `warning` | Yes | Detect forecast versions missing a recorded fallback tier. |
| `prediction_explanation_missing` | `warning` | Yes | Detect prediction-backed forecasts missing methodology explanation text. |
| `episodic_cadence_mismatch` | `warning` | Yes | Detect episodic projects whose spread does not use episodic timing logic. |
| `milestone_shape_mismatch` | `warning` | Yes | Detect milestone-driven projects whose largest months do not align to milestones. |

## Implementation Notes

- Runtime rule logic lives in [validation.py](/Users/thoberry/Desktop/CODEX/Quotes4/apps/api/app/modules/forecasts/validation.py).
- Structured warnings are returned on forecast responses as `sanityChecks` at line, version, and detail level.
- Hard failures still flow into the existing `issues` list only when a rule is marked blocking (`severity = error`), so warnings do not stop normal draft iteration.
- Focused unit coverage lives in [test_forecast_sanity_checks.py](/Users/thoberry/Desktop/CODEX/Quotes4/apps/api/tests/test_forecast_sanity_checks.py).
- Scenario-driven integration coverage lives in [test_forecast_validation.py](/Users/thoberry/Desktop/CODEX/Quotes4/apps/api/tests/test_forecast_validation.py).

## UI Recommendations

| Severity | UI treatment | Recommendation |
| --- | --- | --- |
| `error` | Persistent blocking banner on the forecast header plus inline row/month highlighting | Prevent submit/lock, show exact affected line or month, and provide a corrective action hint. |
| `warning` | Dismissible banner or callout in the forecast summary plus badges on affected lines | Keep the forecast editable, but make the warning visible in the default view so operators do not need to hunt for it. |
| `info` | Secondary badge or tooltip | Use for provenance and model-context signals that inform trust without implying action is required. |

### Suggested placement

- Forecast header: show version-level and detail-level warnings, grouped by severity.
- Monthly cards/table: highlight month-specific checks like early revenue, missing actual replacement, or rollup mismatches.
- Discipline rows: show line-level badges for delivery timing, shaped-curve mismatches, and narrow-band warnings.
- Scenario compare view: surface `scenario_outputs_too_similar` directly in the scenario summary so users know the comparison is commercially weak.
- Confidence UI: show confidence score beside metadata completeness or data sufficiency when `confidence_too_high_for_metadata` or `narrow_bands_sparse_data` fires.
- Submission flow: show blocking `error` checks in the confirmation panel before submit/lock is attempted.
