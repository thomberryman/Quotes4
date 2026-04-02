# Predicted Spend Advisory Contract (Strict)

## Purpose

This contract defines **predicted spend** as advisory intelligence only, explicitly separated from revenue forecasting.

- Predicted spend answers: "What cost/spend is likely?"
- Revenue forecast answers: "What revenue should be recognized and when?"

These are different data products and must remain separate in storage, APIs, and UI rendering.

## 1) Exact API / JSON Shapes

### 1.1 Project-level predicted spend

```json
{
  "project_id": "proj_123",
  "predicted_spend_low": 120000,
  "predicted_spend_expected": 145000,
  "predicted_spend_high": 172000,
  "confidence_score": 0.74,
  "data_sufficiency_score": 0.69,
  "fallback_tier": "discipline_history_only",
  "explanation_summary": "Expected spend leans above quoted baseline due to historical overrun in finishing and tight schedule duration.",
  "comparable_project_refs": [
    {
      "project_id": "proj_987",
      "similarity_score": 0.86,
      "rationale": "Similar format, discipline mix, and schedule length."
    }
  ],
  "prediction_timestamp": "2026-04-02T12:45:11Z",
  "prediction_version": "spend-v2.3.0"
}
```

### 1.2 Discipline-level predicted spend

```json
[
  {
    "project_id": "proj_123",
    "discipline": "online",
    "predicted_spend_low": 36000,
    "predicted_spend_expected": 44000,
    "predicted_spend_high": 54000,
    "confidence_score": 0.72,
    "main_drivers": [
      "historical conform rework",
      "current posted spend floor"
    ],
    "variance_risk": "high"
  }
]
```

### 1.3 Quote comparison view

```json
{
  "quoted_total": 158000,
  "predicted_spend_total": 145000,
  "quoted_vs_predicted_gap": 13000,
  "discipline_comparison_rows": [
    {
      "discipline": "online",
      "quoted_amount": 47000,
      "predicted_spend_expected": 44000,
      "quoted_vs_predicted_gap": 3000,
      "quoted_vs_predicted_gap_pct": 0.0682,
      "variance_risk": "high"
    }
  ]
}
```

### 1.4 Advisory UI state

```json
{
  "state": "sparse_data_low_confidence",
  "reason_code": "low_sufficiency",
  "message": "Prediction is available but based on thin comparable cost history.",
  "stale_after_hours": 168,
  "advisory_acted_by_user_id": null,
  "advisory_acted_at": null
}
```

### 1.5 Full response envelope

```json
{
  "project_level_predicted_spend": {},
  "discipline_level_predicted_spend": [],
  "quote_comparison_view": {},
  "advisory_ui_state": {}
}
```

## 2) UI Component Contract

Use one top-level UI contract that mirrors the API shape and keeps predicted spend data isolated from revenue UI state.

```ts
interface PredictedSpendAdvisoryContract {
  project_level_predicted_spend: ProjectLevelPredictedSpend;
  discipline_level_predicted_spend: DisciplineLevelPredictedSpend[];
  quote_comparison_view: QuoteComparisonView;
  advisory_ui_state: AdvisoryUiState;
}
```

### Required UI behavior by state

- `loading`: show skeletons; suppress stale values unless explicitly cached-labeled.
- `no_prediction_available`: show empty advisory state with guidance to refresh/run prediction.
- `sparse_data_low_confidence`: show warning badge and explanation summary by default.
- `stale_prediction`: show timestamp and stale warning; allow refresh action.
- `overridden`/`ignored`: show immutable banner with actor + timestamp metadata where available.

## 3) Validation Rules

### Numeric and ordering rules

- `predicted_spend_low <= predicted_spend_expected <= predicted_spend_high` at both project and discipline level.
- `confidence_score` and `data_sufficiency_score` must be in `[0, 1]`.
- Monetary values must be non-negative.

### Identity and completeness rules

- `project_id` is required and non-empty on project-level and discipline-level entries.
- Every discipline row must have a stable `discipline` key.
- `prediction_timestamp` must be a valid ISO-8601 UTC timestamp.
- `prediction_version` is required for auditability.

### Referential rules

- `comparable_project_refs[].project_id` must be unique per response.
- Every `discipline_comparison_rows[].discipline` must exist in `discipline_level_predicted_spend`.

### UI-state rules

- `state = stale_prediction` requires `prediction_timestamp` older than configured freshness threshold.
- `state = overridden | ignored` should include `advisory_acted_*` metadata when available.

## 4) Rules to Keep Spend Separate From Revenue Forecast Data

1. **No shared persistence object**: do not store predicted spend in forecast version tables or forecast write models.
2. **No cross-field leakage**: predicted spend payload must not contain fields like `forecast_version_id`, `monthly_revenue`, `weighted_revenue`, or revenue forecast allocations.
3. **No automatic writes**: predicted spend cannot auto-update quote totals, forecast totals, phasing rows, or dashboard forecast aggregates.
4. **Explicit labeling in UI**: all predicted spend surfaces must be labeled advisory and non-binding.
5. **Independent timestamps and versions**: spend prediction freshness/versioning must be tracked independently from forecast versions.
6. **Override scope isolation**: override/ignore actions apply only to spend advisory state and must not mutate revenue forecast scenario data.

## Reference Implementation

See `packages/contracts/src/predicted-spend-contract.ts` for the strict TypeScript contract and runtime validation helpers.
