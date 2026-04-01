# Controlled Vocabulary Seed and Schema Recommendations

## Purpose

This document turns the controlled vocabulary into an implementation plan for the current PostgreSQL backend design.

It distinguishes between:

- values that can be seeded immediately with the current schema
- values that should remain enums
- schema changes that should land before import automation, analytics, and prediction logic rely on the vocabulary

## Seed Artifacts Added

The active seed path now runs through [apps/api/app/seed.py](/Users/thoberry/Desktop/CODEX/Quotes4/apps/api/app/seed.py) via `npm run db:seed`.

Legacy Prisma seed artifacts under `packages/db/src/seeds` remain in the repo only as archival reference and should not be treated as the active source of seeded schema behavior.

These seed:

- `disciplines`
- `reference_data_values` categories for:
  - `service`
  - `deliverable`
  - `quote_line_item_subcategory`
  - `project_format`
  - `pipeline_stage`
  - `revenue_category`
  - `actuals_mapping_category`
  - `counterparty_tag`

## What Should Stay as Enums

Keep these in code and schema as enums because they drive workflow behavior and are already stable:

- `ProjectStatus`
- `ProjectOutcomeType`
- `CompanyClassificationType`
- `ProjectPartyRole`
- `QuoteLineItemType`
- `PdfExtractionRunStatus`
- `ExtractionReviewStatus`
- `CetaImportStatus`
- `CetaRowStatus`
- `ActualMappingDecisionStatus`
- `MappingMethod`
- `ForecastAllocationMethod`
- `ForecastVersionStatus`

These should not be duplicated into `reference_data_values`.

## Current Seed Strategy

### `disciplines`

Use the dedicated `disciplines` table because it is already relationally important across:

- projects
- quotes
- extraction results
- actuals mapping
- forecast lines

### `reference_data_values`

Use `reference_data_values` for lower-risk controlled vocabularies that need:

- labels
- sort order
- active flags
- metadata
- future admin maintenance

### Metadata contract for seeded reference data

Until dedicated relational tables exist, use `reference_data_values.metadata` with these keys:

- `parentGroupKey`
- `disciplineKey`
- `mapsToProjectStatus`
- `synonyms`
- `description`
- `systemDefined`

This metadata is appropriate for seed baselines and UI/reference usage, but it is not enough on its own for audit-ready import normalization. Alias matching should move into a dedicated table.

## Recommended Schema Changes

## 1. Add `reference_term_aliases`

Priority: high, before production PDF and CETA normalization.

Purpose:

- preserve raw source terms
- make alias-to-canonical mapping reviewable
- scope mappings by source system and field

Suggested table:

| Column                  | Type             | Notes                                                                |
| ----------------------- | ---------------- | -------------------------------------------------------------------- |
| `id`                    | `text`/UUID/cuid | Primary key                                                          |
| `category`              | `text`           | Matches a vocabulary family such as `discipline` or `project_format` |
| `alias_text`            | `text`           | Raw alias as entered or imported                                     |
| `normalized_alias_text` | `text`           | Lowercased and normalized for matching                               |
| `canonical_key`         | `text`           | Canonical key in the target vocabulary                               |
| `source_system`         | `text null`      | Example: `pdf`, `ceta`, `manual`                                     |
| `source_field_path`     | `text null`      | Example: `line_item.description`, `vendor_name`                      |
| `confidence_hint`       | `numeric null`   | Optional default confidence for auto-suggestions                     |
| `is_active`             | `boolean`        | Soft deactivate obsolete aliases                                     |
| `created_at`            | timestamp        | Audit trail                                                          |
| `updated_at`            | timestamp        | Audit trail                                                          |

Suggested indexes:

- unique on `(category, normalized_alias_text, coalesce(source_system, ''), coalesce(source_field_path, ''))`
- index on `(category, canonical_key, is_active)`

## 2. Add explicit pipeline stage storage on `projects`

Priority: high, before pipeline analytics and forecast weighting.

Recommendation:

- add `projects.pipeline_stage_key text null`
- keep `projects.status` as the coarse operational enum
- validate `pipeline_stage_key` against seeded `reference_data_values` category `pipeline_stage` in the service layer

Reason:

- `ProjectStatus` is intentionally coarse
- analytics and forecasting usually need finer distinctions inside `bid` and `active`

## 3. Normalize project format storage

Priority: high, before comparable-project scoring becomes production logic.

Current state:

- `project_metadata.formatType` is a free-text field

Recommendation:

- replace or augment it with `project_metadata.project_format_key text null`
- validate it against `reference_data_values` category `project_format`
- keep `contentType` and `contentSubtype` as secondary descriptive fields

Reason:

- comparable-project logic should use a controlled format axis
- free-text `formatType` will drift and weaken prediction quality

## 4. Add explicit quote classification fields

Priority: high, before quote ingestion and margin reporting mature.

Recommended additions to `quote_line_items`:

- `subcategory_key text null`
- `revenue_category_key text null`

Optional later additions:

- `service_key text null`
- `deliverable_key text null`

Recommended usage:

- `line_type` remains the base enum for workflow behavior
- `subcategory_key` drives reporting and import normalization
- `revenue_category_key` supports dashboards, forecasting slices, and prediction features
- `service_key` and `deliverable_key` should be added only when the quote builder or import review UI needs that level of precision

## 5. Add explicit actuals spend-category storage

Priority: high, before actuals-vs-forecast analytics are trusted.

Recommended additions:

- `actual_mapping_decisions.actuals_mapping_category_key text null`
- `mapped_actuals.actuals_mapping_category_key text null`

Optional upstream staging support:

- `ceta_import_rows.suggested_actuals_mapping_category_key text null`

Reason:

- the current schema maps actuals to project and discipline only
- spend-nature reporting needs its own controlled axis
- predictions will likely need both discipline and spend-category history

## 6. Add soft company tagging if needed

Priority: medium.

Core company roles already exist as enums through:

- `company_classifications`
- `project_parties`

If the business needs softer labels such as `agency` or `brand`, add a join table instead of widening enums immediately.

Suggested table:

- `company_reference_tags`
  - `company_id`
  - `reference_data_value_id` or `tag_key`
  - unique on `(company_id, tag)`

Use this for:

- agencies
- brands
- freelancers
- internal entities

Do not use it to replace core roles like `client` or `production_company`.

## 7. Decide how far discipline hierarchy should go

Priority: medium.

The current `disciplines` table is strong enough for primary operational use, but the hierarchy currently lives only in seed conventions.

Recommended options:

1. Keep hierarchy in code or metadata for phase 1.
2. Add `parent_group_key` to `disciplines` if the UI and dashboards need stable grouping soon.
3. Add a dedicated `discipline_groups` table only if group management becomes a business-admin workflow.

Option 2 is the best near-term tradeoff.

## Validation Strategy

Until more fields are normalized, use these rules:

- validate seeded key columns in the application layer against the expected category
- reject unknown keys during write operations
- preserve raw imported text in staging tables even when a canonical key is stored
- record who approved alias mappings and actual mappings

## Rollout Order

1. Seed `disciplines` and `reference_data_values` using `npm run db:seed`.
2. Add `reference_term_aliases`.
3. Add `projects.pipeline_stage_key` and `project_metadata.project_format_key`.
4. Add `quote_line_items.subcategory_key` and `quote_line_items.revenue_category_key`.
5. Add actuals mapping category fields to mapping and approved-actual tables.
6. Add optional company tags if the business needs them.
7. Promote any high-traffic vocabulary from `reference_data_values` to a dedicated table only after it proves to need stronger relational behavior.

## Recommendation Summary

Use the current schema to seed the controlled vocabulary now, but do not stop at seed data.

Before production ingestion, forecasting analytics, and comparable-project prediction logic depend on this vocabulary, add:

- alias tracking
- explicit pipeline stage storage
- explicit project format storage
- explicit quote classification fields
- explicit actuals spend-category fields

That sequence preserves operational clarity, keeps mappings explainable, and avoids hiding business logic inside free text or JSON.
