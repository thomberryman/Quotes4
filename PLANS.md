# Unified Forecast Engine Extension

## Summary

- Extend the existing `apps/api` forecast engine instead of introducing a second planning path.
- Make `ForecastVersion` the single auditable forecast record, with predictive modules supplying explainable timing, confidence, scenario, and calibration inputs directly into forecast generation.
- Replace the current `schedule` versus `manual` split with richer allocation profiles, sequencing-aware timing, partial-actual assimilation, version deltas, and scenario-aware aggregation while preserving editable operator overrides.

## Delivery Steps

1. Inspect and document the current forecast, prediction, API, UI, and worker flow so the implementation is grounded in the existing system rather than duplicating it.
2. Extend the forecast data model for unified explainability and reforecasting: scenario key, engine source, method metadata, confidence/data-sufficiency scores, fallback tier, actual-assimilation markers, version change summaries, per-line explanatory inputs, and per-month range bands.
3. Add forecast profile and sequencing support inside the forecast engine itself: front-, mid-, and back-loaded curves, episodic cadence, milestone weighting, schedule compression or delay handling, and discipline sequencing templates with overlap assumptions and override storage.
4. Refactor prediction integration so `revenue_spread`, scenario, probability, and comparable evidence feed normalized forecast inputs into the forecast service instead of remaining a separate planning output that later gets copied into manual forecast lines.
5. Extend forecast recalculation to support dynamic reforecasting on quote changes, schedule edits, actuals imports, and forecast-line overrides while preserving immutable version history, explicit delta reasons, and “why this changed” metadata.
6. Blend partial actuals into forecast generation by replacing completed months or discipline portions with posted actuals, reforecasting only the remaining work, and storing divergence indicators against predicted timing and amount assumptions.
7. Add scenario-aware forecast versions for `base`, `upside`, and `downside`, keeping scenario results versioned and selectable without overwriting the base forecast, and support separate operational versus commercial weighted views for pipeline work.
8. Add project and portfolio aggregation reads that roll forecasts up by month, client, discipline, stage, and scenario without double counting and with separate booked versus probability-weighted totals.
9. Extend forecast and project APIs so the frontend can retrieve unified explainability, scenario versions, confidence bands, version deltas, and aggregation views from the forecast module.
10. Upgrade the forecast and scenario UI to show spread curves, forecast-versus-actual overlays, confidence ranges, scenario toggles, version comparisons, and explicit override controls tied back to the unified forecast record.
11. Add regression coverage around allocation profiles, sequencing effects, partial actual assimilation, reforecast versioning, scenario outputs, confidence ranges, and aggregation correctness using realistic post-production examples.

## Checks

- `npm run contracts:generate`
- `npm run lint`
- `npm run typecheck`
- `npm run test`
- `npm run build`

## Assumptions

- The existing `forecasts` module remains the single source of truth for forecast outputs; prediction runs remain persisted evidence and editable assumptions, not a parallel forecast engine.
- Backwards compatibility is preserved by keeping existing schedule/manual behaviour as explicit fallback tiers while richer methods are added incrementally.
- Dashboard work in this pass should move from fixture-only forecast summaries toward real forecast aggregation reads, but it should not trigger a full dashboard redesign.

## Follow-on Tranche

1. Replace fixture-backed dashboard portfolio forecast sections with reads from persisted `ForecastVersion`, `ForecastLine`, and `MonthlyForecastAllocation` data so project and portfolio views share one forecast source.
2. Add scenario-aware dashboard filtering so base, upside, and downside rollups can be viewed at portfolio level without overwriting current/base forecast records.
3. Use persisted forecast confidence, confidence bands, actual overlays, and benchmark data in dashboard summaries and drilldowns rather than deriving synthetic confidence from fixture metadata.
4. Preserve existing dashboard structure and readability while tightening its data provenance; this tranche should improve trust in the numbers, not redesign the dashboard information architecture.

# Forecast Accuracy Evaluation

## Summary

- Add a forecast-accuracy evaluation read to `apps/api` so seeded/sample data can be measured from persisted forecasts, mapped actuals, benchmark summaries, and prediction evaluations.
- Keep the output operational and explainable: separate complete-project accuracy from partial monthly tracking, show discipline and scenario weak spots explicitly, and derive recommendations from measured error patterns.
- Reuse the existing forecast and prediction records instead of introducing a parallel analytics store or one-off script.

## Delivery Steps

1. Add forecast accuracy response schemas covering headline metrics, project comparisons, monthly variance, discipline variance, confidence calibration, scenario accuracy, weakest areas, and recommendations.
2. Implement a forecast service read that aggregates current forecast versions against benchmark actuals and mapped actuals, keeping complete and partial evidence paths distinct.
3. Build monthly variance tracking from persisted monthly forecast allocations and actual month coverage where mapped actuals exist, including coverage counts so gaps remain visible.
4. Build discipline-level variance tracking from forecast line totals versus benchmark or mapped actual discipline totals, and rank the weakest disciplines by observed absolute error.
5. Reuse persisted prediction runs and evaluations to summarize confidence calibration and scenario tracking, while explicitly calling out missing resolved scenario evidence when coverage is sparse.
6. Expose the analysis through a forecast API endpoint and add regression coverage against the seeded demo dataset for metrics, weakness detection, and recommendation generation.

## Checks

- `npm run test -w @quotes4/api -- test_forecasts.py`
- `npm run lint -w @quotes4/api`
- `npm run build -w @quotes4/api`

## Assumptions

- “Sample data” refers to the repository’s seeded demo projects and the persisted forecast, benchmark, mapped-actual, and prediction-run records they generate.
- Complete-project accuracy should only use projects with complete actual benchmarks; partial actuals still contribute to monthly tracking and coverage visibility.
- Recommendations should remain deterministic and evidence-based, not generic prose disconnected from the measured forecast errors.

## Next Risk Reduction

1. Move forecast curve profiles and discipline sequencing templates into persisted forecast configuration using `reference_data_values` metadata so the engine reads editable, auditable assumptions before falling back to built-in defaults.
2. Keep the existing forecast engine as the only allocator: configuration records should parameterize the engine, not create another planning path or duplicate predictive timing logic.
3. Expose the active profile and sequencing catalogue through forecast policy responses so the UI can show which assumptions are available and currently governing timing.
4. Add focused regression coverage proving database-backed configuration changes materially influence monthly timing and sequencing behaviour.

# Manual Project Intake

## Summary

- Add a manual project-intake entry point on the projects page for work that exists before a bid PDF is ready to import.
- Keep the flow explicit and operational: a visible add button, a focused data-entry box, and immediate project-list feedback after creation.
- Reuse the existing audited project create endpoint rather than introducing a separate intake-only backend path.

## Delivery Steps

1. Expose project creation through the shared TypeScript API client so the web app can create records from a client-side form.
2. Add a projects-page add button that opens a manual-entry dialog with the core project fields needed before bid import.
3. Validate required fields and date ordering before submission, then surface API errors clearly when creation fails.
4. Refresh the projects list state immediately after successful creation so operators can continue into the appropriate workspace.
5. Add focused regression coverage for the new validation and any backend guardrails introduced for manual entry.

## Checks

- `npm run test -- tests/web/form-validation.test.ts`
- `npm run test -w @quotes4/api -- test_backend_mvp.py`
- `npm run typecheck`

## Assumptions

- Manual intake in this pass covers the core project record and does not attempt full client/contact/discipline setup in the same dialog.
- Project creation should remain available before quote import, with status defaulting to bid unless the operator explicitly chooses another valid status.

# Forecast Commercial Validation

## Summary

- Validate the existing forecast, predictive, scenario, and dashboard logic against realistic post-production commercial cases rather than only technical happy paths.
- Add a scenario catalogue, automated regression coverage, and a short written report that calls out where the current heuristics are commercially credible and where they can still mislead operators.
- Reuse the current forecast engine, prediction modules, and dashboard rollups directly so the validation suite measures shipped behaviour instead of a parallel model.

## Delivery Steps

1. Catalogue realistic core scenarios, edge cases, and failure-pattern cases around revenue spread, discipline timing, pipeline weighting, scenario outputs, confidence bands, partial actual assimilation, schedule-change reforecasting, and rollups.
2. Add focused automated tests that exercise the existing services and APIs with post-production shaped data, asserting commercial sanity checks instead of only response shape.
3. Add structured runtime sanity checks with severity and blocking behaviour so suspicious outputs can be surfaced to operators without waiting for regression tests to fail.
4. Surface blocking and warning checks in the forecast workspace UI so operators see top-level banners, scenario and confidence callouts, inline month or line flags, and repeated blocking errors before submit or lock.
5. Record suspicious-but-current behaviours, rule severity, and UI surfacing guidance in short validation docs, including cases where the engine can return plausible numbers with weak underlying evidence.
6. Run the targeted API and web test suites plus the relevant frontend build or type checks, then capture any residual gaps or untested risks in the handoff.
7. Resolve remaining frontend verification gaps by fixing the Next server chunk emission issue blocking `@quotes4/web` builds and by aligning dashboard filter coverage with the current default-scenario behaviour.

## Checks

- `npm run test -w @quotes4/api -- test_forecasts.py`
- `npm run test -w @quotes4/api -- test_predictions.py`
- `npm run test -w @quotes4/api -- test_dashboards.py`

## Assumptions

- This pass validates the current deterministic logic; it should not introduce a separate calibration engine or rewrite the forecast heuristics.
- “Commercially credible” means the timing, weighted values, and scenario movement match how post-production revenue is expected to land operationally, even when the engine is intentionally heuristic.

# Predictive Layer Maturation

## Summary

- Replace the earlier one-shot predictive guidance slice with a persisted, modular predictive layer built on top of the existing comparable, benchmark, forecast, and UI foundations.
- Keep the logic deterministic, explainable, editable, and auditable, with explicit fallback tiers and maturity-aware behaviour instead of opaque model artefacts.
- Deliver the first substantial maturity pass around hybrid predictive input capture, persisted prediction runs, richer quote/discipline/monthly/risk/win-probability outputs, and scenario planning that can promote into an editable forecast draft.

## Delivery Steps

1. Add the highest-value typed schema fields for prediction quality and reporting: `projects.pipeline_stage_key`, `projects.bid_owner_user_id`, `projects.strategic_account_flag`, `project_metadata.project_format_key`, `quote_versions.pricing_context_json`, `quote_line_items.subcategory_key`, and `quote_line_items.revenue_category_key`.
2. Add persistence tables for `prediction_runs`, `prediction_module_outputs`, `prediction_run_comparables`, `prediction_scenarios`, `prediction_overrides`, and `prediction_evaluations`, using prediction runs as the source of truth for guidance, scenarios, overrides, and evaluation metadata.
3. Refactor the current prediction flow into deterministic modules for feature snapshots, fallback selection, quote guidance, discipline prediction, revenue spread, risk/anomaly scoring, win probability, scenario generation, confidence scoring, explanations, and evaluation, while preserving and reusing the current heuristic work where it still holds up.
4. Keep `GET /api/v1/projects/{project_id}/predictive-guidance`, but have it surface the latest persisted expected-scenario summary enriched with maturity stage, readiness, sufficiency, fallback tier, scenario, win-probability, and audit context. Add project-scoped endpoints for creating/listing/fetching runs, saving overrides, and promoting scenarios to forecast drafts.
5. Standardize prediction behaviour by maturity stage: Stage 1 sparse opportunity, Stage 2 structured quote development, Stage 3 awarded/booked work, and Stage 4 in-flight work with actuals blending.
6. Standardize fallback tiers across modules: `in_flight_actuals`, `high_similarity_history`, `same_client_format_budget_band`, `same_project_type_all_clients`, `discipline_baseline`, and `system_default`, and persist which tier was used together with the evidence supporting it.
7. Extend quote guidance to output total ranges, discipline ranges, omitted-discipline flags, quote-position flags, comparable evidence, and user acceptance or override state.
8. Extend discipline predictions to output likely quoted amount, likely actual amount, variance %, risk level, confidence, data sufficiency, and key drivers per discipline.
9. Replace the simple monthly interpolation logic with profile-aware forecasting that supports front-loaded, even, back-loaded, episodic, and milestone-style spreads, adjusted by sequencing, schedule compression, delayed start or delivery, and in-flight actuals.
10. Add explainable win-probability scoring using transparent weighted factors derived from stage, relationship history, pricing position, revision activity, timeline realism, strategic account signals, and comparable historical outcomes.
11. Extend risk and anomaly scoring to cover likely overruns, underquoted scope, unrealistic monthly spread, unusual discounting, high third-party exposure, atypical quote composition, schedule slippage risk, and sparse-data warnings.
12. Add a Scenario Planning workspace under the project navigation that compares base, upside, and downside scenarios, exposes editable assumptions, shows discipline and monthly impacts, captures audit state, and can promote a selected scenario into a draft forecast.
13. Expand the predictive and comparable UI surfaces to show fallback tier, feature readiness, data sufficiency, top drivers, comparable evidence, and accept or override controls, plus predictive input capture for project metadata and quote pricing context.
14. Keep the operational dashboard out of a full replatform in this pass. Only thread prediction or scenario summaries into project-scoped flows that can already be backed by real persisted run data.

## Checks

- `npm run contracts:generate`
- `npm run lint`
- `npm run typecheck`
- `npm run test`
- `npm run build`

## Assumptions

- This remains deterministic and explainable. No black-box model artefacts, hidden optimisation layers, or external training infrastructure are introduced.
- Only the highest-value predictive inputs become first-class columns in this pass. Broader feature capture lands in validated structured JSON until repeated use justifies more normalization.
- Prediction persistence is the operational record for runs, scenarios, overrides, and evaluation history. Accepted scenarios may create forecast drafts, but they do not overwrite quote versions or locked forecasts automatically.
- Full dashboard replatforming is deferred because the current dashboard implementation is still fixture-backed. Project-scoped prediction and scenario integration lands first.

# Demo Auth Default Alignment

## Summary

- Replace the invalid `.local` demo admin email with a validator-safe address across seed data, test defaults, and the web login screen.
- Keep the local setup path consistent so the seeded demo user and the login form use the same credentials.
- Verify the local auth endpoint accepts the seeded credentials after reseeding.

## Delivery Steps

1. Update the seeded admin default email in the API seed path and test defaults to a validator-safe value.
2. Update the web login form defaults and helper copy to match the seeded credentials.
3. Reseed or provide the required local reseed command so existing local databases pick up the new admin email.
4. Verify the auth session endpoint accepts the demo login payload.

## Checks

- `npm run db:seed`
- `curl -X POST http://localhost:3001/api/v1/auth/session ...`

## Assumptions

- Changing the local demo admin email is acceptable because this is seeded development data, not user-entered production data.
- The existing demo password remains unchanged.

# Follow-up MVP Hardening

## Summary

- Add CSRF protection for cookie-authenticated unsafe API requests without breaking bearer-token API clients.
- Move application-facing file access off raw storage URLs onto authenticated API downloads.
- Add database-backed protection against duplicate active jobs and expose clearer failure visibility for operators.
- Persist failed authentication attempts into the audit trail and extend tests around the new hardening paths.

## Delivery Steps

1. Issue a readable CSRF cookie with session creation/refresh, require `X-CSRF-Token` for unsafe cookie-authenticated requests, and wire the browser API client to send it automatically.
2. Replace raw storage-facing file links with authenticated API download URLs and add a protected file download endpoint.
3. Add a partial unique index for active job deduplication keys, handle dedupe races safely in the job service, and extend job listing with filtered operator-facing failure summaries.
4. Persist failed auth attempts into audit logs using an independent transaction so security anomalies survive request rollbacks.
5. Regenerate API contracts, add focused regression tests, and run lint, typecheck, test, and build.

## Checks

- `npm run contracts:generate`
- `npm run lint`
- `npm run typecheck`
- `npm run test`
- `npm run build`

## Assumptions

- Full project-scoped authorization remains deferred because the current schema has no user-to-project assignment model.
- The first-party web app continues to use cookie auth; bearer tokens remain available for non-browser/API compatibility in this pass.
- Authenticated API downloads are an acceptable immediate replacement for direct storage URLs while full signed-storage delivery remains deferred.

# MVP Hardening Review

## Summary

- Eliminate browser-readable session token handling for the main web flow and enforce safer auth defaults.
- Tighten role enforcement around privileged quote-ingestion approval actions.
- Add server-side validation for uploads, import payloads, and worker callbacks.
- Remove unsafe object loading paths that currently allow arbitrary local-file or remote-URL reads outside controlled storage keys.
- Improve background job reliability with deduplication, terminal-state handling, and stricter worker result correlation.
- Add targeted frontend validation to the main login and import/upload workflows.
- Extend test coverage around the highest-risk auth, upload, import, and worker scenarios.

## Delivery Steps

1. Harden auth/session handling so API auth can use secure cookies, the web app no longer depends on browser-readable access tokens, and insecure production defaults are rejected.
2. Add reusable validation helpers for uploaded filenames, content types, checksums, payload text bounds, and storage object keys, then apply them to file upload and import endpoints.
3. Restrict quote-ingestion preview and storage access to registered storage keys only, removing arbitrary local-path and remote-URL reads outside test mode.
4. Tighten role enforcement and callback validation for quote ingestion and actuals-import worker flows, including job correlation and duplicate-job prevention.

# Demo And Live Environment Split

## Summary

- Keep the existing seeded demo workflow available as a separate environment for walkthroughs, training, and regression checks.
- Add a second environment for real imports with its own database, storage namespace, auth cookie namespace, and operator-facing labeling so it can run alongside demo safely.
- Make the live environment seed only baseline operational data and admin access, not demo projects or sample imports.

## Delivery Steps

1. Extend runtime configuration so API and web can expose an environment label, workspace description, data mode, and auth cookie names from environment variables instead of hard-coded demo defaults.
2. Split API seeding into baseline versus demo modes so both environments receive required roles, reference data, and admin access, while only demo receives sample projects, forecasts, and imports.
3. Update auth cookie handling in API and web so demo and live instances can both run on `localhost` without session collision.
4. Update the login and shell UI to clearly identify whether the operator is in the demo workspace or the live-import workspace, including copy that warns when the environment is intended for real data.
5. Parameterize Docker Compose ports, database names, storage bucket names, and service-facing URLs so the same stack definition can be launched twice with separate env files.
6. Add checked-in environment templates and README guidance for running `demo` and `live` stacks side by side, including migration and seed commands for each environment.
7. Add focused regression coverage around seed modes and configurable auth cookies so the environment split remains auditable and safe.

## Checks

- `npm run test -w @quotes4/api -- test_backend_mvp.py test_seed_demo_data.py`
- `npm run lint -w @quotes4/api`
- `npm run lint -w @quotes4/web`
- `npm run typecheck -w @quotes4/web`

## Assumptions

- “Real data” means an operator-managed environment intended for live imports and manual data entry, not a multi-tenant production deployment with external identity or infrastructure changes.
- Running demo and live side by side on one machine is valuable enough to justify environment-specific cookie names and port separation.
- Separate storage buckets are desirable alongside separate databases so uploaded live source files do not mix with demo assets.
5. Add focused frontend validation and clearer failure handling for login, PDF ingestion, and CETA import setup.
6. Add regression tests for the hardened flows and run the relevant API, worker, web, and repo-level checks.

## Checks

- `npm run lint`
- `npm run typecheck`
- `npm run test`

## Assumptions

- This pass focuses on the MVP’s highest-risk operational gaps and does not attempt a full authorization model redesign.
- Existing demo/test login flows remain usable in `development` and `test`, but insecure production defaults must fail closed.
- Storage access in automated tests may continue to use local fixture paths when `APP_ENV=test`; non-test environments must use controlled object keys only.

# Repo Integration Cleanup and Live Variance Workspace

## Summary

- Treat `apps/api` as the only active schema and migration owner.
- Remove `packages/db` from active build, lint, typecheck, and runtime-facing workspace paths.
- Eliminate active contract duplication by relying on generated contract types for API clients.
- Harden quote APIs with project scoping and server-side financial validation.
- Replace the pending project `actuals-vs-quote` page with a live benchmark-backed workspace.

## Delivery Steps

1. Update workspace scripts, TypeScript references, Docker wiring, and docs so SQLAlchemy/Alembic in `apps/api` is the active schema path and `packages/db` is legacy reference only.
2. Fix generated contract handling for empty object schemas, remove handwritten inline client response types, and regenerate OpenAPI-driven contract output.
3. Add optional project scoping to quote listing and enforce deterministic quote subtotal/total validation on the backend.
4. Add a project-level `actuals-vs-quote` read model and route backed by existing benchmark summary tables.
5. Replace the pending web page with a live variance workspace and remove obsolete pending navigation/config code.
6. Add focused API and web tests, then run lint, typecheck, tests, build, and formatting checks relevant to the touched files.

## Checks

- `npm run lint`
- `npm run typecheck`
- `npm run test`
- `npm run build`
- `npm run format:check`

## Assumptions

- No database migration is needed because the variance workspace will reuse existing benchmark summary tables.
- `packages/db` remains in-repo as an archived reference and is not part of the active runtime path.
- Future-only schema ideas documented in legacy design notes, including `notes` and `assumptions`, stay deferred in this pass.

# Forecast UI Usability Pass

## Summary

- Rework the forecast workspace around real operator tasks instead of a single long editor form.
- Make monthly timing, scenario context, confidence ranges, override state, version comparison, and forecast explanations visible without hunting through the page.
- Keep the changes within the existing forecast API surface so sales, ops, and finance can share one auditable screen.

## Delivery Steps

1. Reorganize the forecast page header and version controls so users can quickly identify the active scenario, lifecycle status, quote basis, and confidence posture.
2. Replace the plain monthly table with clearer month cards and rollups that surface weighted values, confidence bands, actual overrides, and month-to-month variance at a glance.
3. Add a scenario-focused summary and a lightweight version comparison view so users can compare base, upside, downside, and parent-version deltas without leaving the forecast workspace.
4. Reshape line editing around override workflows by exposing schedule/manual mode, rationale capture, risk signals, and explanation visibility more explicitly before the save action.
5. Add focused web tests for any new forecast presentation helpers and run the relevant lint, typecheck, and test checks for the touched web code.

## Checks

- `npm run lint -w @quotes4/web`
- `npm run typecheck -w @quotes4/web`
- `npm run test -- tests/web/*`

## Assumptions

- This pass improves usability and visibility using already-exposed forecast fields; it does not add new backend endpoints or schema changes.
- The forecast editor remains the main project-scoped workspace for review and overrides, with richer navigation inside the existing page rather than a separate forecast console.
