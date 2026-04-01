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
