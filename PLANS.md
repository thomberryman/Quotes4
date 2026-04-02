# Unified Dashboard Forecast Contract

## Summary

- Return a strict `forecastDataset` contract from `GET /api/v1/dashboards/operational`.
- Keep the forecast module as the source of truth for project/month/status/discipline forecast data.
- Treat legacy dashboard forecast sections as temporary derived views while the UI completes the switch to `forecastDataset`.

## Delivery Steps

1. Build and validate the strict dashboard contract in `apps/api/app/modules/forecasts/service.py`.
2. Return that contract from the operational dashboard response model instead of the richer internal projection.
3. Keep existing dashboard sections running from the same forecast dataset source while preserving separate quote totals.
4. Add regression coverage for contract shape, reconciliation, version fallback, actuals assimilation, mixed allocation methods, and empty windows.

# Revenue Trust Realignment

## Summary

- Keep the existing dashboard as the primary output surface and preserve its current charts, tables, filters, and layout.
- Move forecast ownership back into the forecasts module so the dashboard stops rebuilding a parallel revenue truth model.
- Separate commercial quote value from forecast value, keep comparable and predictive outputs advisory, and make the pipeline from comparable -> quote -> forecast -> dashboard explicit and consistent.

## Delivery Steps

1. Add a forecast-owned dashboard projection contract in `apps/api/app/modules/forecasts` that returns one canonical project/month/discipline forecast view from a selected `ForecastVersion`.
2. Include the fields the dashboard needs directly in that contract: project and client ids/names, canonical commercial status, operational status, quote version id, forecast version id, scenario key, quote total, forecast total, probability, execution dates, allocation method/profile, override flags, project monthly values, and discipline monthly values.
3. Refactor `apps/api/app/modules/dashboards/service.py` to consume that forecast-owned projection instead of reconstructing month rollups and totals from `ForecastVersionRead`.
4. Keep the existing dashboard response shape intact, but derive `monthlyRevenueForecast`, `forecastRevenue`, and sales-pipeline totals from the canonical projection so charts and tables reconcile to one source.
5. Preserve quote totals separately from forecast totals across dashboard and forecast read models so scenario-promoted or recalculated forecasts do not overwrite commercial quote value reporting.
6. Centralize manual allocation normalization in the forecasts service so line-level allocation edits and revenue-phasing row edits both use the same validation, locking, note persistence, and recalculation semantics.
7. Keep both edit surfaces live, but make them converge on the same stored `MonthlyForecastAllocation` override model and exclude unsaved phasing drafts from dashboard truth.
8. Extend the quote builder to fetch predictive guidance for the selected quote version and render it as compact advisory evidence without auto-generating quote sections or line items.
9. Add focused regressions proving dashboard totals reconcile from the canonical forecast projection, quote and forecast totals remain distinct, manual allocation writes behave the same across both edit surfaces, and quote-version-scoped predictive guidance renders in the builder.

## Unified Dashboard Contract

The canonical forecast projection must expose:

- `project_id`, `project_name`, `client_id`, `client_name`
- `commercial_status` with `estimated | awarded | lost`
- `operational_status` with current lifecycle values such as `bid | awarded | active | complete | lost`
- `quote_version_id`, `forecast_version_id`, `scenario_key`
- `total_project_value`
- `forecast_total_value`
- `probability_percent`
- `execution_start_date`, `execution_end_date`
- `allocation_method_used`
- `allocation_profile_key`
- `override_flags.has_manual_overrides`
- `override_flags.has_locked_months`
- `override_flags.has_actualized_months`
- `project_months[]` with `month`, `amount`, `weighted_amount`, `actual_amount`, `booked_amount`
- `discipline_months[]` with the same month payload plus discipline identity

## Checks

- `source .venv/bin/activate && set -a && source .env && set +a && cd apps/api && pytest tests/test_dashboards.py tests/test_forecasts.py tests/test_forecast_validation.py tests/test_predictions.py -q`
- `vitest run tests/web/revenue-phasing-workspace.test.tsx tests/web/forecast-editor-helpers.test.ts tests/web/dashboard-helpers.test.ts tests/web/quote-builder-workspace.test.tsx`
- `npm run typecheck`

## Assumptions

- Dashboard visuals stay as they are; only data ownership, naming, and wiring change.
- `commercial_status` becomes canonical for dashboard contracts, while current operational statuses remain available for compatibility with existing UI filters and labels.
- Comparable and prediction outputs stay advisory in this pass and do not auto-write quote or forecast records.
- “Predict real spend” remains out of scope for dashboard surface changes here; this pass is about making the revenue dashboard trustworthy.
- Both forecast edit surfaces remain available, but they must share one override persistence and recalculation path.

# Advisory Spend Prediction In Scenarios

## Summary

- Add spend prediction as advisory output in the scenario workspace only.
- Keep revenue-outturn guidance and spend/cost guidance distinct.
- Do not feed spend guidance into forecasts, phasing, quote totals, or the dashboard.

## Delivery Steps

1. Extend prediction context to load mapped actual cost summaries for comparable projects alongside the target project.
2. Add a spend-prediction module in `apps/api/app/modules/predictions` that predicts total and discipline spend from comparable cost actuals with current target cost actuals as the floor.
3. Extend scenario outputs with `spend_summary` and discipline spend rows, and have scenario levers carry those values forward without affecting revenue promotion logic.
4. Update contracts and the scenario workspace to render a compact `Advisory Spend Outlook` section while renaming the existing discipline table to clarify it remains revenue-outturn guidance.
5. Add focused regressions for spend-summary API output, scenario spend scaling, fallback behavior on thin cost history, and scenario UI rendering.

## Assumptions

- Spend means project cost/outlay derived from mapped cost actuals.
- Revenue-outturn guidance remains the existing `predictedActualAmount` and variance signal.
- Comparable cost history comes from mapped cost actuals on comparable projects, not benchmark revenue variance.
- Thin cost evidence should surface as fallback or unavailable, not fabricated totals.

# Strict Predicted Spend Advisory Contract

## Summary

- Define a strict, explicit predicted spend advisory contract that is independent from revenue forecast contracts.
- Cover project-level spend, discipline-level spend, quote-vs-predicted comparison, and advisory UI state handling.
- Provide runtime validation helpers so consumers can enforce ordering/score/state rules.

## Delivery Steps

1. Add shared contract types for predicted spend in `packages/contracts/src/predicted-spend-contract.ts`.
2. Export contract types from `packages/contracts/src/index.ts` for API/UI consumers.
3. Document exact JSON shapes, UI state contract, validation rules, and separation rules in `docs/predicted-spend-contract.md`.
4. Run contracts typecheck to confirm compile health.
