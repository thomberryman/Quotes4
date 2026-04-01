# PostgreSQL Relational Database Design

This document defines the approved operational database design for Quotes4. The active backend implementation lives in the SQLAlchemy models and Alembic migrations under [apps/api](/Users/thoberry/Desktop/CODEX/Quotes4/apps/api).

The legacy Prisma package under `packages/db` is retained only as archival reference material and is not part of the active schema, migration, or runtime ownership path.

## 1. Schema design

### Design principles

- Keep the system of record in PostgreSQL and treat versioned financial data as append-only.
- Prefer explicit, queryable columns for business-critical facts over opaque JSON blobs.
- Separate ingestion/staging tables from approved operational tables so review remains traceable.
- Keep counterparties normalized so the same organization is not duplicated as a client, streamer, broadcaster, competitor, and vendor.
- Make audit entries first-class records and keep future note or assumption storage explicit rather than hidden in ad hoc text fields.

### Core domains

- Access control: `users`, `roles`, `permissions`, `role_permissions`, `user_role_assignments`
- Reference/master data: `reference_data_values`, `companies`, `company_classifications`, `contacts`, `contact_roles`, `company_contacts`, `disciplines`, `loss_reasons`
- Project operations: `projects`, `project_metadata`, `project_parties`, `project_contacts`, `project_disciplines`, `project_schedule_ranges`, `project_outcomes`
- Quote management: `quotes`, `quote_versions`, `quote_sections`, `quote_line_items`
- Files and ingestion: `uploaded_files`, `project_files`, `quote_version_files`, `pdf_extraction_runs`, `pdf_extraction_field_results`, `pdf_extraction_line_item_results`, `ceta_imports`, `ceta_import_rows`
- Actuals and forecasting: `actual_mapping_decisions`, `mapped_actuals`, `forecasts`, `forecast_versions`, `forecast_lines`, `monthly_forecast_allocations`
- Operational narrative and traceability: `audit_logs`
- Explainable historical learning: `comparable_project_links`

### Counterparty strategy

Clients, production companies, studios, streamers, broadcasters, competitors, and vendors are modeled through:

- `companies`: the shared legal/commercial organization master
- `company_classifications`: one company can carry multiple classifications such as `client` and `streamer`
- `project_parties`: the role a company plays on a specific project, such as `client`, `production_company`, or `competitor`

This avoids duplicate records for organizations like Netflix or BBC Studios that can play multiple roles.

For reporting or admin UX clarity, the database can expose filtered SQL views such as `client_companies`, `production_companies`, `studio_companies`, `streamer_companies`, and `broadcaster_companies` without duplicating the underlying data.

## 2. Table definitions

### Access control

- `users`: internal users, invitation state, activation state, and display identity
- `roles`: named role bundles such as `system_admin` or `finance_analyst`
- `permissions`: granular capabilities such as `quotes.issue` or `forecasts.lock`
- `role_permissions`: many-to-many bridge between roles and permissions
- `user_role_assignments`: many-to-many bridge between users and roles, with assignment provenance

### Master data and counterparties

- `companies`: shared organization master for all external counterparties
- `company_classifications`: typed classifications for each company
- `contacts`: person-level contacts, independent of any single organization
- `contact_roles`: controlled vocabulary for contact functions
- `company_contacts`: company-to-contact affiliations with role, title, department, and primary flag
- `disciplines`: controlled vocabulary for post-production disciplines
- `loss_reasons`: structured reasons for lost work
- `reference_data_values`: generic controlled lists for lower-risk categories such as currencies or future dropdowns

### Projects

- `projects`: the operational project header, lifecycle status, currency, and key dates
- `project_metadata`: optional one-to-one descriptive and reporting fields such as content type, runtime, episode count, and budget target
- `project_parties`: which companies are attached to the project and in what role
- `project_contacts`: which contacts matter for the project, optionally tied back to a company and a contact role
- `project_disciplines`: disciplines in scope for the project
- `project_schedule_ranges`: date ranges used for schedule-based forecasting
- `project_outcomes`: append-only commercial outcome events for bid, award, and loss decisions

### Quotes

- `quotes`: stable quote container per project
- `quote_versions`: immutable quote revisions with totals, issue state, and provenance
- `quote_sections`: ordered groupings inside a quote version
- `quote_line_items`: ordered line items with discipline, quantity, rate, amount, and line type

### Files and ingestion

- `uploaded_files`: immutable object-storage metadata and file lineage
- `project_files`: project-level attachments
- `quote_version_files`: quote-level attachments, including issued PDFs
- `pdf_extraction_runs`: one parsing/review lifecycle per uploaded quote PDF
- `pdf_extraction_field_results`: extracted scalar fields from a PDF, with confidence and review state
- `pdf_extraction_line_item_results`: extracted line-item candidates from a PDF, with confidence and review state
- `ceta_imports`: one CETA upload/review/approval lifecycle per file
- `ceta_import_rows`: row-level immutable staging records from CETA

### Actuals and forecasts

- `actual_mapping_decisions`: review decisions that map staging rows to project/discipline targets
- `mapped_actuals`: approved operational actuals, always traceable back to the source row when applicable
- `forecasts`: stable project-level forecast container
- `forecast_versions`: immutable forecast revisions
- `forecast_lines`: per-version forecast rows, usually one per discipline or forecast bucket
- `monthly_forecast_allocations`: month-by-month allocations for each forecast line

### Narrative and audit

- `audit_logs`: append-only business event log with before/after snapshots and metadata

`notes` and `assumptions` remain future schema candidates described in historical design work. They are not part of the current SQLAlchemy runtime model set and should not be treated as implemented tables.

## 3. Relationships

- A `user` can hold many roles through `user_role_assignments`.
- A `role` can grant many permissions through `role_permissions`.
- A `company` can have many classifications and many contacts.
- A `project` can have many parties, many contacts, many disciplines, many schedule ranges, many quote records, many actuals, and many audit log entries.
- A `project` has at most one `project_metadata` row and one active `forecast` container.
- A `quote` belongs to one project and has many `quote_versions`; one version can be marked as current.
- A quote's `current_version_id` must always point to a version owned by that same quote.
- A `quote_version` has many `quote_sections`; each section has many ordered `quote_line_items`.
- An `uploaded_file` can be attached to projects or quote versions and can also be the source file for PDF extraction runs and CETA imports.
- A `pdf_extraction_run` has many extracted fields and many extracted line-item candidates; it can optionally point to the quote version approved from that extraction.
- A `ceta_import` has many `ceta_import_rows`; each row can have many mapping decisions and at most one approved `mapped_actual`.
- A `forecast` belongs to one project and has many `forecast_versions`; one version can be marked as current.
- A forecast's `current_version_id` must always point to a version owned by that same forecast.
- A `forecast_version` has many `forecast_lines`; each line has many `monthly_forecast_allocations`.
- Future `notes` or `assumptions` tables, if added later, should use explicit ownership constraints rather than implicit JSON-only storage.

## 4. Indexing recommendations

### Included in schema now

- Unique identifiers for version sequencing:
  - `quote_versions (quote_id, version_number)`
  - `forecast_versions (forecast_id, version_number)`
  - `monthly_forecast_allocations (forecast_line_id, month)`
  - `ceta_import_rows (ceta_import_id, row_number)`
- Common operational filters:
  - `projects (status, updated_at)`
  - `quotes (project_id, updated_at)`
  - `pdf_extraction_runs (status, created_at)`
  - `ceta_imports (status, uploaded_at)`
  - `mapped_actuals (project_id, work_date)`
  - `audit_logs (entity_type, entity_id, created_at)`

### Add in SQL migrations after the initial baseline

- Partial unique indexes for primary selections:
  - one primary `project_parties` row per `(project_id, role)` where `is_primary = true`
  - one primary `company_contacts` row per `company_id` where `is_primary = true`
  - one primary `project_contacts` row per `(project_id, contact_id)` where `is_primary = true`
- Check constraints:
  - `project_schedule_ranges.end_date >= start_date`
  - `monthly_forecast_allocations.month` is the first day of the month
  - if future `notes` are added, exactly one parent FK per row
  - if future `assumptions` are added, exactly one parent FK per row
- Search indexes:
  - trigram GIN indexes on company name, contact full name, and project name for fuzzy lookup
- Scale-oriented indexes when tables grow:
  - BRIN on `audit_logs.created_at`
  - BRIN on `ceta_import_rows.work_date`
  - GIN on selected JSON columns only if query workload justifies it

## 5. Migration strategy

### Recommended rollout

1. Create a baseline migration from the new schema before production data exists.
2. If migrating from the current MVP schema, use an expand-migrate-contract approach rather than destructive renames in one step.
3. Introduce new shared tables first:
   - `companies`, `company_classifications`, `contacts`, `contact_roles`, `company_contacts`
   - `forecasts`, `forecast_versions`, `forecast_lines`
   - `uploaded_files`, `project_files`, `quote_version_files`
4. Backfill legacy rows into new structures:
   - `Client`, `ProductionCompany`, `StudioAccount`, `StreamerBroadcaster` into `companies` plus `company_classifications`
   - `ProjectContact` rows into `contacts` plus `project_contacts`
   - `ForecastPlan` rows into `forecasts`, `forecast_versions`, `forecast_lines`, and `monthly_forecast_allocations`
   - `ImportBatch` and staging rows into `pdf_extraction_*` or `ceta_import_*` depending on type
5. Cut application code over to the new tables and keep dual-write only if a staged rollout is required.
6. Add raw SQL constraints and partial indexes after backfill cleanup.
7. Remove or archive superseded legacy tables once validation queries show parity.

### Data quality checks during migration

- Every quote must keep version ordering and an optional valid `current_version_id`.
- Every quote current-version pointer must reference a version owned by the same quote.
- Every mapped actual created from CETA must retain a valid `source_ceta_import_row_id`.
- Forecast version totals must equal the sum of their forecast lines and line allocations.
- Every forecast current-version pointer must reference a version owned by the same forecast.
- Lost outcomes with a competitor or loss reason should remain queryable after backfill.

## 6. Structured columns vs JSON

### Use structured columns for

- Lifecycle state and dates
- Money values, quantities, units, and currencies
- Foreign-key relationships
- Searchable/filterable operational fields:
  - discipline
  - project status
  - outcome type
  - quote version status
  - forecast allocation method
  - loss reason
  - contact role

### Use JSON only for

- `audit_logs.before_json`, `audit_logs.after_json`, `audit_logs.metadata`
- `project_metadata.metadata` for long-tail descriptive fields that are not yet stable enough to normalize
- `pdf_extraction_field_results.source_bounds` for parser coordinates
- `ceta_import_rows.raw_payload` for full source-row preservation
- `reference_data_values.metadata` for low-risk UI extensions
- `comparable_project_links.reasons_json` because the reasoning payload is explanatory and append-only

### Decision rule

If the application will filter, join, validate, aggregate, or report on a field, it should be a structured column. JSON is reserved for raw source preservation, append-only audit context, and genuinely unstable long-tail attributes.

## 7. Sample records for realistic projects

The examples below show how the schema supports both an awarded project and a lost bid.

### Example organizations

| Table                     | Key values                                                                                                                   |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `companies`               | `cmp_netflix` = Netflix, `cmp_sister` = Sister Pictures, `cmp_bbcs` = BBC Studios, `cmp_halo` = Halo Post                    |
| `company_classifications` | Netflix: `streamer`, BBC Studios: `client` and `broadcaster`, Sister Pictures: `production_company`, Halo Post: `competitor` |
| `contacts`                | `con_jane_liu` Jane Liu, `con_marc_evans` Marc Evans                                                                         |
| `contact_roles`           | `executive_producer`, `finance`, `post_supervisor`                                                                           |

### Awarded project

| Table                     | Sample row                                                                                                                    |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `projects`                | `prj_blackglass_s1`, code `BGS1-TRAILER`, name `Black Glass S1 Launch Campaign`, status `active`, quote currency `GBP`        |
| `project_metadata`        | content type `series trailer`, genre `drama`, runtime `90`, episode count `8`, duration weeks `14`, budget target `185000.00` |
| `project_parties`         | BBC Studios as `client` primary, Sister Pictures as `production_company` primary, Netflix as `streamer` primary               |
| `project_contacts`        | Jane Liu linked to BBC Studios as `executive_producer`, Marc Evans linked to Sister Pictures as `post_supervisor`             |
| `project_disciplines`     | picture, gfx, online, sound, colour                                                                                           |
| `project_schedule_ranges` | `Editorial Prep` 2026-04-06 to 2026-04-24, `Finishing` 2026-04-27 to 2026-05-29                                               |
| `project_outcomes`        | `bid` at 2026-03-18, `awarded` at 2026-03-27                                                                                  |

### Quote and forecast records

| Table                          | Sample row                                                                                                                  |
| ------------------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| `quotes`                       | `qte_blackglass_main` for `prj_blackglass_s1`                                                                               |
| `quote_versions`               | v1 draft total `172500.00`, v2 issued total `181250.00`, current version = v2                                               |
| `quote_sections`               | `Offline`, `Finishing`, `Audio`, `Deliverables`                                                                             |
| `quote_line_items`             | `Offline 15 days @ 850`, `Colour 6 days @ 1200`, `5.1 Mix 2 days @ 950`, `Mastering Package`                                |
| `forecasts`                    | one forecast container for `prj_blackglass_s1`                                                                              |
| `forecast_versions`            | v1 submitted total `181250.00`, v2 locked total `179900.00`, current version = v2                                           |
| `forecast_lines`               | Picture schedule-based `68000.00`, GFX manual `42000.00`, Sound schedule-based `18500.00`, Colour schedule-based `16800.00` |
| `monthly_forecast_allocations` | Apr 2026 `74200.00`, May 2026 `89650.00`, Jun 2026 `16050.00` across the forecast lines                                     |

### Files, PDF extraction, CETA, and mapped actuals

| Table                              | Sample row                                                                                                                 |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `uploaded_files`                   | `upl_quote_v2_pdf` quote PDF, `upl_ceta_apr_2026` CETA export                                                              |
| `quote_version_files`              | v2 linked to `upl_quote_v2_pdf` as issued quote PDF                                                                        |
| `pdf_extraction_runs`              | extraction run on `upl_quote_v2_pdf`, parser `azure-document-intelligence`, status `approved`                              |
| `pdf_extraction_field_results`     | `quote.total = 181250.00`, `project.client = BBC Studios`, `currency = GBP`                                                |
| `pdf_extraction_line_item_results` | candidate line item `Colour Grade`, qty `6`, rate `1200.00`, amount `7200.00`, review status `approved`                    |
| `ceta_imports`                     | April 2026 import, status `approved`, row count `148`                                                                      |
| `ceta_import_rows`                 | row 27 `Flame conform`, work date `2026-04-28`, amount `2350.00`, suggested project `prj_blackglass_s1`, status `approved` |
| `actual_mapping_decisions`         | row 27 mapped to discipline `online`, method `suggested`, decision `approved`                                              |
| `mapped_actuals`                   | approved actual linked back to CETA row 27, amount `2350.00`, work date `2026-04-28`                                       |

### Lost bid example

| Table              | Sample row                                                                                          |
| ------------------ | --------------------------------------------------------------------------------------------------- |
| `projects`         | `prj_neon_district`, code `ND-TRAILER`, status `lost`                                               |
| `project_parties`  | client `BBC Studios`, competitor `Halo Post`                                                        |
| `project_outcomes` | `bid` at 2026-02-11, `lost` at 2026-02-20 with competitor `Halo Post` and loss reason `price_lower` |
| `audit_logs`       | append-only record of the lost-work decision, including client feedback metadata where needed       |
