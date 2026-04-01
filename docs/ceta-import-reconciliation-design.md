# CETA Import and Reconciliation Workflow Design

## Purpose

This design defines a review-first workflow for importing structured CETA exports into Quotes4.

The goal is to preserve raw source data, make mapping logic explainable, support repeated imports across a project's lifecycle, and compare quote expectations against approved actuals without pretending the source data is more exact than it really is.

## Design Principles

- Preserve the original uploaded export and every parsed source row immutably.
- Use structured staging plus explicit review queues instead of silent auto-posting.
- Record why a mapping was suggested or approved, not just the final target.
- Separate raw source terms from canonical project, discipline, cost-category, and revenue-category values.
- Treat each import as a new versioned batch, never an in-place edit of a previous import.
- Compare quote, forecast, and actuals only at grains the data can genuinely support.

## 1. Import Workflow

1. Upload and register the batch.
   - Store the original file in `uploaded_files` with `file_category = ceta_export`.
   - Create a `ceta_imports` row for the batch with source metadata, import scope, and coverage dates.
   - Capture `source_system`, `source_export_id` when available, `source_exported_at`, and a file checksum.

2. Parse into immutable staging.
   - A worker reads the file and writes one immutable `ceta_import_rows` record per source row.
   - Each row stores both structured normalized fields and the untouched `raw_payload`.
   - Parsing never writes directly to `mapped_actuals`.

3. Validate and classify the staged rows.
   - Run file-level checks such as unsupported format, missing headers, encoding issues, or mixed currencies.
   - Run row-level checks such as missing project code, invalid dates, zero-value rows, duplicate rows, and sign/category inconsistencies.
   - Classify each row as `cost`, `revenue`, or `ignore/review`, but only when the source data supports that confidently.

4. Generate explainable mapping suggestions.
   - Suggest project matches from external project code links, prior approved mappings, and scoped aliases.
   - Suggest discipline, cost category, and revenue category from controlled aliases and admin-managed mapping rules.
   - Store multiple candidates with scores and explanations rather than a single hidden guess.

5. Move the batch into review.
   - Set `ceta_imports.status` to `in_review` once parsing and initial validation finish.
   - Surface work queues for blocking errors, ambiguous mappings, likely duplicates, repeat-import changes, and large quote-vs-actual deltas.

6. Resolve rows in a review UI.
   - Reviewers accept a suggestion, override it, reject the row, or mark it as linked to an existing approved actual.
   - Reviewers can save a correction as a reusable scoped rule, but only with explicit intent.
   - Every row must end in a clear outcome before batch approval.

7. Preview reconciliation before approval.
   - Show import totals by month, discipline, and category next to prior approved actuals, the current quote version, and the current forecast version.
   - Highlight rows that would create new actuals, supersede prior actuals, or duplicate existing approved rows.

8. Approve and post.
   - Approval writes approved row decisions into `mapped_actuals` or links a row to an existing current actual when it is a true repeat.
   - The approval step records audit events, reviewer notes, and any supersession decisions.
   - Trigger `dashboard_refresh` and any forecast variance recalculation that depends on actuals.

9. Preserve history.
   - Rejected and failed batches remain queryable with their original file, parsed rows, issues, and reviewer actions.
   - Later imports never overwrite earlier raw data or review history.

## 2. Staging Tables

The current schema already has strong foundations in `ceta_imports` and `ceta_import_rows`. To support robust review and repeat-import handling, the staging layer should be extended as follows.

### `ceta_imports`

Purpose: one immutable import batch per uploaded CETA file.

Recommended fields in addition to the current schema:

| Field | Purpose |
| --- | --- |
| `source_export_id` | Source-system export identifier when present. |
| `source_exported_at` | When CETA produced the export, separate from upload time. |
| `coverage_start` / `coverage_end` | Business period covered by the file. |
| `coverage_mode` | `snapshot`, `incremental`, or `unknown`; drives repeat-import logic. |
| `supersedes_import_id` | Optional explicit lineage to an earlier import batch. |
| `parse_summary_json` | Counts for parsed rows, errors, warnings, duplicates, and candidate coverage. |
| `review_summary_json` | Counts for approved rows, rejected rows, linked repeats, and superseded actuals. |

Notes:

- Keep `uploaded_at`, `reviewed_at`, and `approved_at` as milestone timestamps.
- Keep approval batch-level; row-level resolution still happens before approval.

### `ceta_import_rows`

Purpose: immutable row-level staging with normalized fields plus the untouched source payload.

Recommended fields in addition to the current schema:

| Field | Purpose |
| --- | --- |
| `source_row_uid` | Stable source row identifier if the export provides one. |
| `row_hash` | Hash of the full normalized row content for exact-repeat detection. |
| `business_key_hash` | Hash of the business identity of the row, used to detect corrections across imports. |
| `normalized_project_code` | Trimmed and normalized source project code. |
| `normalized_vendor_name` | Normalized vendor/supplier text for rule matching. |
| `normalized_description` | Normalized description text for alias and rule matching. |
| `financial_type` | `cost`, `revenue`, or `review_required`. |
| `matched_current_actual_id` | Optional link to the currently approved actual this row matches during review. |
| `duplicate_group_key` | Groups exact duplicates inside the same file or overlapping files. |

Notes:

- Keep `raw_payload` even if the row's fields are also projected into structured columns.
- Do not mutate a staged row after parse time except for workflow fields such as review status references.

### `ceta_import_row_issues`

Purpose: explicit row-level and batch-level review blockers and warnings.

Recommended fields:

| Field | Purpose |
| --- | --- |
| `ceta_import_row_id` | Nullable for batch-level issues, required for row issues. |
| `severity` | `fatal`, `blocking`, `warning`, or `info`. |
| `issue_code` | Stable machine-readable code such as `unknown_project_code`. |
| `field_name` | Optional source field tied to the issue. |
| `message` | Reviewer-friendly description. |
| `details_json` | Parse context, candidate IDs, or comparison payload. |
| `resolved_at` / `resolved_by_id` | Resolution tracking for manual review. |

### `ceta_import_row_candidates`

Purpose: keep multiple explainable suggestions per row and per mapping dimension.

Recommended fields:

| Field | Purpose |
| --- | --- |
| `ceta_import_row_id` | Row under review. |
| `dimension` | `project`, `discipline`, `cost_category`, `revenue_category`, or `financial_type`. |
| `target_type` | Entity family or reference-data family. |
| `target_id_or_key` | FK or canonical key of the candidate target. |
| `candidate_source` | `external_reference`, `alias`, `rule`, `historical_match`, or `manual_seed`. |
| `score` | Confidence score used only for ranking suggestions. |
| `explanation` | Plain-language reason shown in the UI. |
| `sort_order` | Candidate ordering for reviewer presentation. |

Notes:

- A candidate table is preferred over overloading `suggestedProjectId` and `suggestedDisciplineId` because the workflow must support four mapping dimensions and more than one candidate per dimension.
- If convenient for filtering, the top candidate can still be mirrored onto the row record.

## 3. Mapping Model

The mapping model should separate reusable reference data from per-row approval decisions.

### Canonical mapping dimensions

Every approved row should resolve to the following business dimensions:

| Dimension | Requirement |
| --- | --- |
| Project | Required for all posted actuals. |
| Discipline | Optional when the source genuinely cannot support it, but the gap must remain visible. |
| Financial type | Required and mutually exclusive: `cost` or `revenue`. |
| Cost category | Required for `cost` rows; sourced from `actuals_mapping_category`. |
| Revenue category | Required for `revenue` rows; sourced from `revenue_category`. |

### Reusable mapping sources

1. `project_external_reference` table
   - New table mapping source-system project codes or names to internal `projects`.
   - Supports exact matching before fuzzy or rule-based matching.

2. `reference_term_alias`
   - Reuse the existing controlled-vocabulary alias pattern for discipline, cost-category, and revenue-category aliases.
   - Scope aliases by source system and field path where useful.

3. `actual_mapping_rules`
   - New admin-managed rule table for patterns such as vendor plus description contains text, source discipline code, or source account code.
   - Rules should be scoped where possible by source system and optionally project.
   - Store a human-readable rule label and explanation so reviewers understand why a rule fired.

4. Prior approved decisions
   - If a row's `business_key_hash` closely matches a previously approved row, use that prior mapping as a candidate source.
   - Never silently auto-approve on history alone when the amount or dates materially changed.

### Approval decision record

Extend `actual_mapping_decisions` so it becomes the final row-level decision snapshot.

Recommended additions:

| Field | Purpose |
| --- | --- |
| `financial_type` | Final approved classification. |
| `mapped_cost_category_key` | Canonical cost category for cost rows. |
| `mapped_revenue_category_key` | Canonical revenue category for revenue rows. |
| `approval_action` | `post_new`, `supersede_existing`, `link_existing`, or `reject`. |
| `matched_existing_actual_id` | Actual row linked during repeat-import review when applicable. |
| `explanation_json` | Provenance per dimension, such as alias ID, rule ID, or manual override reason. |

Notes:

- The decision record should preserve what the reviewer approved at that time, even if rules or aliases change later.
- Manual corrections should optionally offer "save as reusable rule" or "save as project-specific external reference", but those must be explicit reviewer actions.

### Posted actual record

Extend `mapped_actuals` so posted actuals are category-aware and version-safe.

Recommended additions:

| Field | Purpose |
| --- | --- |
| `financial_type` | `cost` or `revenue`. |
| `cost_category_key` | Canonical cost category when `financial_type = cost`. |
| `revenue_category_key` | Canonical revenue category when `financial_type = revenue`. |
| `actual_business_key` | Stable logical key used for repeat-import supersession. |
| `supersedes_mapped_actual_id` | Prior current actual replaced by this approval, if any. |
| `is_current` | Flags the row that dashboards should use. |
| `change_type` | `new`, `corrected`, `withdrawn`, or `repeat_linked`. |

## 4. Reconciliation Workflow

Reconciliation should happen at two levels: row-level approval and project-level variance review.

### Row-level reconciliation

Each staged row should land in one of these review buckets:

- `blocking_issue`: cannot be approved until resolved or rejected.
- `ambiguous_mapping`: candidate scores are too close or too weak.
- `repeat_match`: row appears to match an already current approved actual.
- `changed_repeat`: row appears to replace or correct a prior approved actual.
- `ready_to_post`: mapping is approved and no unresolved blocker remains.

Reviewer actions:

- Accept a suggested mapping and post a new actual.
- Override one or more dimensions, with a note when the change is material.
- Link the row to an existing current actual if the row is a true repeat from a later snapshot import.
- Reject a row that is out of scope, clearly duplicated, or not a valid operational actual.

### Project-level reconciliation

Before approving the batch, show a reconciliation summary against three baselines:

1. Prior approved actuals
   - Identify new rows, corrected rows, unchanged repeats, and possible withdrawals.

2. Current quote version
   - Compare approved actuals against quote line rollups and amount-bearing assumptions.

3. Current forecast version
   - Compare approved actuals-to-date against forecast allocations by month and discipline.

Recommended review surfaces:

- Import summary by month, discipline, financial type, and category.
- Top unmapped or manually overridden rows by amount.
- Repeat-import diff summary for overlapping periods.
- Variance cards showing where actuals materially exceed or lag quote and forecast baselines.

Approval rule:

- A batch cannot be approved until every staged row is resolved as `post_new`, `supersede_existing`, `link_existing`, or `reject`.

## 5. Validation and Error Handling

Validation should distinguish between parse failure, batch blockers, and row-level review work.

### Severity model

| Severity | Behavior |
| --- | --- |
| `fatal` | Batch fails parsing or cannot produce trustworthy staging rows. |
| `blocking` | Import stays in review until the issue is resolved or the row is rejected. |
| `warning` | Import can still be approved, but the warning remains visible. |
| `info` | Non-blocking context such as likely repeat rows or benign rounding differences. |

### Batch-level checks

- Unsupported file type or broken structure.
- Missing required header set for the declared source-system template.
- Entire file cannot be decoded or parsed consistently.
- Mixed currency file when the import policy requires single-currency review.
- Coverage dates missing when the import is marked as a snapshot.

### Row-level checks

- Unknown or missing external project code.
- Invalid work date or posting date.
- Missing amount or non-numeric amount.
- Zero-value row that is not explicitly allowed by rule.
- Financial type cannot be inferred safely.
- Cost row without cost category candidate coverage.
- Revenue row without revenue category candidate coverage.
- Duplicate row within the same import.
- Row outside the project's active date window, kept as a warning unless business policy says otherwise.

### Error-handling behavior

- Preserve the file and any parsed rows even when the batch lands in `failed`.
- Never drop rows because they are malformed; represent the problem as an issue whenever possible.
- Show blocking counts and total blocked amount in the review inbox.
- Require reviewer notes for material overrides and for approving rows with unresolved warnings above a threshold.

## 6. Repeat-Import and Version Handling

Repeat imports are expected across a project's lifecycle, so the workflow must distinguish between a new row, a true duplicate, and a correction.

### Core rules

1. Every uploaded file creates a new immutable `ceta_imports` batch.
2. Repeat handling depends on `coverage_mode`.
   - `snapshot`: the file is intended to represent the full covered period.
   - `incremental`: the file only contains new or changed rows.
   - `unknown`: do not infer missing rows as withdrawals.
3. Use both `row_hash` and `business_key_hash`.
   - `row_hash` detects exact repeats.
   - `business_key_hash` detects likely corrections to the same logical actual.

### Expected row outcomes on re-import

| Outcome | Meaning |
| --- | --- |
| `new` | No prior current actual matches the business key in the covered scope. |
| `repeat_linked` | The row exactly matches an existing current actual and should not create a duplicate posting. |
| `corrected` | The row matches a prior business key but changes amount, date, or mapping and should supersede the current actual. |
| `withdrawn` | A previously current row disappears from a later snapshot import covering the same scope and should be marked inactive only after review. |

### Posting strategy

- Keep `mapped_actuals` immutable and version-aware.
- Use `is_current` plus `supersedes_mapped_actual_id` so dashboards can read the latest approved state while audit history remains intact.
- For `repeat_linked` rows, do not create a duplicate `mapped_actuals` record. Instead, capture the link in the decision record and the import review summary.
- Only infer `withdrawn` rows from later snapshot imports, never from incremental imports.

### Import lineage

Track lineage explicitly at the batch level:

- `supersedes_import_id` when a later file is known to replace an earlier one.
- overlap summaries showing which prior imports cover the same period and project scope.
- audit events for approval decisions that create, supersede, or withdraw current actuals.

## 7. Variance Analysis Logic

Variance logic should prefer honest rollups over brittle one-to-one attribution.

### Comparison grains

Use the highest-confidence shared grain available:

1. Project by month
2. Project by discipline and month
3. Project by discipline, financial type, and month
4. Project by discipline, category, and month

Do not claim row-level actual-to-quote matching unless a user explicitly links a row to a quote line or assumption.

### Quote baseline

Use two quote baselines:

- Quote line rollups, grouped by discipline and eventually by revenue category once quote lines support that dimension.
- Amount-bearing assumptions grouped by discipline and optional comparison tags.

Important current-schema note:

- `quote_line_items` and `assumptions` currently support discipline but not explicit cost-category or revenue-category comparison keys.
- Until those keys are added, category-level quote-vs-actual reporting should be limited to rows that users explicitly tag or to project/discipline rollups.

### Recommended formulas

| Metric | Logic |
| --- | --- |
| `actual_amount` | Sum of current approved actuals in the selected grain. |
| `quote_amount` | Sum of quote line items or assumptions in the same grain. |
| `forecast_amount` | Sum of current forecast allocations in the same grain and month. |
| `variance_to_quote` | `actual_amount - quote_amount`. |
| `variance_to_forecast` | `actual_amount - forecast_amount`. |
| `variance_pct` | `variance / baseline` when baseline is non-zero, otherwise null. |
| `unmapped_actual_amount` | Sum of staged rows still unresolved or approved without a discipline/category. |

### Variance interpretation rules

- Show absolute amounts before percentages.
- Keep credits and negative corrections visible as separate line items or drill-down filters.
- Flag large variances even when the mapping is still incomplete, but label them as provisional.
- Narrative assumptions without compatible numeric actuals should appear as review notes, not forced numeric variance metrics.

## 8. Reporting and Dashboard Needs

The workflow needs both operational review screens and durable reporting read models.

### Operational review screens

- Import inbox with status, age, blocked amount, and reviewer ownership.
- Batch detail view with row filters for blockers, warnings, ambiguous mappings, and repeat-import changes.
- Side-by-side row review with raw payload, normalized fields, candidates, prior approved actuals, and quote/forecast context.
- Approval summary showing new, corrected, repeated, withdrawn, and rejected rows.

### Project reporting

- Actuals-to-date vs quote by month and discipline.
- Actuals-to-date vs forecast by month and discipline.
- Cost vs revenue split for a project over time.
- Category breakdown for cost and revenue rows, with drill-down to approved source rows.
- Coverage panel showing last approved import date, covered period, and unresolved staging amount.

### Management dashboards

- Pending import count, blocked import count, and average review age.
- Auto-suggestion coverage and manual override rate.
- Duplicate/repeat rate by source system and project.
- Approved actuals posted this week and net corrected amount from repeat imports.
- Top projects with largest quote-vs-actual and forecast-vs-actual variances.

### Suggested derived read models

- `project_actuals_monthly_summary`
- `project_variance_summary`
- `import_review_summary`
- `mapping_rule_performance_summary`

These should be refreshed asynchronously after import approval rather than recalculated inside the request path.

## Recommended Schema Delta Summary

To implement this design cleanly, Phase 3 should plan for the following schema additions or extensions:

- Extend `ceta_imports` with coverage, lineage, and parse/review summary fields.
- Extend `ceta_import_rows` with repeat-detection hashes, normalized text fields, and a financial-type classification.
- Add `ceta_import_row_issues`.
- Add `ceta_import_row_candidates`.
- Add `project_external_reference`.
- Add `actual_mapping_rules`.
- Extend `actual_mapping_decisions` with financial type, category targets, approval action, and explainability payload.
- Extend `mapped_actuals` with financial type, category targets, supersession fields, and `is_current`.
- Add optional comparison keys to `quote_line_items` and `assumptions` if category-level quote-vs-actual reporting is required.

## Recommended Product Constraints

- Default to review-required when the system cannot distinguish cost from revenue confidently.
- Never auto-create reusable rules from a manual correction.
- Never infer withdrawals from an incremental import.
- Never hide unmapped amounts inside variance summaries; unresolved coverage must stay visible.
- Favor project-, discipline-, month-, and category-level rollups over attempting false line-level precision.
