# Quotes4 Controlled Vocabulary and Data Dictionary

## Purpose

This document defines the controlled vocabulary that Quotes4 should use across quote entry, PDF ingestion, actuals imports, forecasting, dashboards, and comparable-project logic.

The goal is to keep historical analysis explainable and consistent by separating:

- canonical keys stored in the database
- preferred labels shown in the UI
- raw imported terms preserved for audit
- synonym mappings used during ingestion and review

## Canonical Modeling Rules

- Store canonical values as lowercase `snake_case` keys.
- Treat keys as unique within a vocabulary family, not globally.
- Show users the preferred label, not the raw key.
- Preserve source text from PDFs and imports in staging rows for traceability.
- Map imported aliases to a canonical key through reviewable reference data, not hidden code.
- Use broad, stable categories for analytics; use services and deliverables for more detail.
- Prefer dedicated schema models when the system already has one, such as `Discipline`, `Company`, and `ProjectParty`.
- Prefer reference tables when business vocabulary may expand, need alias mapping, or need metadata and sort order.
- Prefer enums only for small, stable workflow states that are tightly coupled to code behavior.

## Enum vs Reference Table Summary

| Category                     | Recommended storage                                                            | Why                                                                                              |
| ---------------------------- | ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------ |
| Disciplines                  | Dedicated `Discipline` model                                                   | Already first-class in the schema and used by quotes, forecasts, actuals, and comparables.       |
| Services                     | `ReferenceDataValue` category `service`                                        | More granular than disciplines and does not yet need its own relational model.                   |
| Deliverables                 | `ReferenceDataValue` category `deliverable`                                    | Output vocabulary changes by client/platform and benefits from alias mapping.                    |
| Quote line item primary type | Enum `QuoteLineItemType`                                                       | Already in the schema and drives base line behavior.                                             |
| Quote line item subcategory  | `ReferenceDataValue` category `quote_line_item_subcategory`                    | Adds analytics and import normalization without turning a stable enum into an uncontrolled list. |
| Project formats              | `ReferenceDataValue` category `project_format` initially                       | Comparable-project logic depends on stable values, but the set can evolve without code changes.  |
| Pipeline stages              | `ReferenceDataValue` category `pipeline_stage` plus mapping to `ProjectStatus` | Business wants finer sales/ops stages than the coarse project lifecycle enum.                    |
| Revenue categories           | `ReferenceDataValue` category `revenue_category`                               | Reporting taxonomy should remain auditable and editable by admins.                               |
| Company classifications      | Enum `CompanyClassificationType`                                               | Stable core roles already present in the schema.                                                 |
| Project party roles          | Enum `ProjectPartyRole`                                                        | Stable project-level counterparty roles already present in the schema.                           |
| Additional counterparty tags | `ReferenceDataValue` category `counterparty_tag` if needed                     | Lets the business add softer labels such as agency or brand without destabilizing core enums.    |
| Actuals mapping categories   | `ReferenceDataValue` category `actuals_mapping_category`                       | Mapping categories vary by source system and should be admin-managed.                            |
| Forecast allocation methods  | Enum `ForecastAllocationMethod`                                                | Small, stable, behavior-driving set already reflected in domain logic.                           |
| Workflow status fields       | Enum per workflow where stable                                                 | Small, operational states with code paths and validation rules.                                  |

## Recommended Supporting Tables

In addition to category-specific tables, add a reusable alias table for import and PDF normalization.

### `reference_term_alias`

| Field                   | Purpose                                                                   |
| ----------------------- | ------------------------------------------------------------------------- |
| `id`                    | Primary key                                                               |
| `category`              | Vocabulary family, for example `discipline`, `service`, `project_format`  |
| `alias_text`            | Raw text to normalize from imports or PDFs                                |
| `normalized_alias_text` | Lowercased/trimmed text used for matching                                 |
| `canonical_key`         | Canonical key in the target reference table                               |
| `source_system`         | Optional source scoping such as `ceta`, `pdf`, `manual`                   |
| `source_field_path`     | Optional source-field scoping such as `line_item.description` or `vendor` |
| `confidence_hint`       | Optional default confidence for auto-suggestions                          |
| `is_active`             | Soft deactivate obsolete aliases                                          |

This keeps synonym handling explicit and reviewable.

## Disciplines

Recommendation: use the existing `Discipline` model, with hierarchy and aliases stored in metadata or supporting reference tables.

Suggested hierarchy:

- `picture_editorial`
- `picture_finishing`
- `audio`
- `localization_delivery`
- `management_ops`

| Canonical key     | Preferred label       | Parent group            | Synonyms to map from imports and PDFs                             | Notes                                                  |
| ----------------- | --------------------- | ----------------------- | ----------------------------------------------------------------- | ------------------------------------------------------ |
| `offline`         | Offline Edit          | `picture_editorial`     | offline, editorial, edit, picture edit, recut                     | Primary picture-editing discipline.                    |
| `edit_assist`     | Edit Assist           | `picture_editorial`     | assistant editor, ae, assist, ingest, sync, prep                  | Support work around editorial prep and turnovers.      |
| `online`          | Online / Conform      | `picture_finishing`     | online, conform, finishing, flame, smoke, finish                  | Final picture assembly and conform work.               |
| `grade`           | Color Grading         | `picture_finishing`     | grade, grading, colour, color correction, di                      | Use `grade` as the key to stay short and consistent.   |
| `vfx`             | Visual Effects        | `picture_finishing`     | visual effects, comp, compositing, cleanup, roto, paint           | Shot-based picture enhancement and fixes.              |
| `graphics`        | Graphics / Titles     | `picture_finishing`     | graphics, gfx, titles, lower thirds, supers, motion design        | Title cards, motion graphics, and on-screen text.      |
| `sound_edit`      | Sound Editorial       | `audio`                 | sound edit, dialogue edit, sfx edit, foley edit                   | Audio editing before final mix.                        |
| `mix`             | Sound Mix             | `audio`                 | mix, dub, dubbing, final mix, rerecording mix                     | Final audio mixing and printmaster work.               |
| `music`           | Music                 | `audio`                 | music supervision, score, music edit, library music               | Music-specific editorial or licensing-related work.    |
| `localization`    | Localization          | `localization_delivery` | subtitles, captions, localisation, dubbing, textless prep         | Language and territory-specific adaptation work.       |
| `qc`              | QC                    | `localization_delivery` | qc, quality control, tech review, technical check                 | Technical and delivery readiness review.               |
| `delivery`        | Delivery / Versioning | `localization_delivery` | delivery, deliverables, versioning, mastering, imf, dcp           | Final package creation and version delivery.           |
| `media_io`        | Media I/O             | `management_ops`        | transcode, io, ingest, exports, archive, restore                  | Media movement, conversion, archive, and restore work. |
| `post_management` | Post Management       | `management_ops`        | post producer, post supervision, project management, coordination | Operational oversight and commercial coordination.     |

## Services

Recommendation: start as `ReferenceDataValue` category `service`, with `discipline_key` and hierarchy stored in metadata. Promote to a dedicated table only if services gain bespoke relationships or operational fields.

| Canonical key            | Preferred label          | Discipline        | Synonyms to map from imports and PDFs            | Notes                                                |
| ------------------------ | ------------------------ | ----------------- | ------------------------------------------------ | ---------------------------------------------------- |
| `editorial_cut`          | Editorial Cut            | `offline`         | edit, cut, assembly, recut                       | Main editorial crafting work.                        |
| `editorial_revision`     | Editorial Revisions      | `offline`         | revisions, notes pass, reversion, recuts         | Iteration after client or producer feedback.         |
| `assistant_edit_prep`    | Assistant Edit Prep      | `edit_assist`     | prep, sync, bins, ingest, turnover prep          | Editorial support service.                           |
| `conform`                | Conform                  | `online`          | conform, online, finishing, relink               | Assembling final timeline from approved sources.     |
| `color_grade`            | Color Grade              | `grade`           | grade, colour pass, color session, grading       | Color treatment and review sessions.                 |
| `vfx_shot_work`          | VFX Shot Work            | `vfx`             | shot work, cleanup, comp, roto, paint            | Discrete VFX work billed by shot, task, or package.  |
| `graphics_build`         | Graphics Build           | `graphics`        | title build, gfx, lower thirds, supers           | Creation or revision of graphics packages.           |
| `sound_edit_service`     | Sound Edit               | `sound_edit`      | dialogue edit, foley edit, sfx edit              | Audio editorial work before mix.                     |
| `adr_foley`              | ADR / Foley              | `sound_edit`      | adr, foley, voice record                         | Session-based replacement or enhancement recording.  |
| `final_mix`              | Final Mix                | `mix`             | mix, final mix, printmaster, dub                 | Client-ready audio mix service.                      |
| `music_edit_supervision` | Music Edit / Supervision | `music`           | music edit, music supervision, score conform     | Music-specific work outside final mix.               |
| `subtitle_caption_prep`  | Subtitle / Caption Prep  | `localization`    | subtitles, captions, sdh, cc prep                | Text-based localization preparation.                 |
| `qc_review`              | QC Review                | `qc`              | qc pass, tech review, compliance check           | Review service before delivery approval.             |
| `versioning`             | Versioning               | `delivery`        | reversion, localization version, alt version     | Building territory, client, or platform variants.    |
| `mastering_packaging`    | Mastering / Packaging    | `delivery`        | mastering, package, imf build, dcp build         | Final container/package creation.                    |
| `media_prep_archive`     | Media Prep / Archive     | `media_io`        | transcode, archive, restore, media prep          | Media logistics and archival support.                |
| `project_management`     | Project Management       | `post_management` | producing, supervision, coordination, management | Oversight, scheduling, and client-facing management. |

## Deliverables

Recommendation: use `ReferenceDataValue` category `deliverable`, with optional parent group and default related service or discipline stored in metadata.

Suggested hierarchy:

- `review`
- `picture_master`
- `audio_master`
- `localization`
- `delivery_package`
- `supporting_assets`

| Canonical key          | Preferred label        | Parent group        | Synonyms to map from imports and PDFs                | Notes                                                |
| ---------------------- | ---------------------- | ------------------- | ---------------------------------------------------- | ---------------------------------------------------- |
| `review_export`        | Review Export          | `review`            | screener, review link, viewing copy, h264            | Temporary or approval-oriented review output.        |
| `final_picture_master` | Final Picture Master   | `picture_master`    | final master, hero master, mezzanine, master file    | Main approved picture deliverable.                   |
| `textless_master`      | Textless Master        | `picture_master`    | textless, clean master, international master         | Picture master without burnt-in titles or captions.  |
| `versioned_master`     | Versioned Master       | `picture_master`    | version, local version, territory version, reversion | Variant of the main master for a platform or market. |
| `trailer_promo_master` | Trailer / Promo Master | `picture_master`    | trailer, promo, teaser                               | Marketing-focused master output.                     |
| `social_cutdown`       | Social Cutdown         | `picture_master`    | social, cutdown, vertical, square, 15s, 30s          | Short-form derived marketing output.                 |
| `final_audio_master`   | Final Audio Master     | `audio_master`      | printmaster, full mix, stems, m&e, split audio       | Client-ready audio deliverable family.               |
| `subtitle_package`     | Subtitle Package       | `localization`      | subtitles, srt, stl, itt                             | Text subtitle files and package components.          |
| `caption_package`      | Caption Package        | `localization`      | captions, closed captions, cc, sdh                   | Accessibility caption deliverables.                  |
| `imf_package`          | IMF Package            | `delivery_package`  | imf, cpl, opl                                        | IMF-based package delivery.                          |
| `dcp_package`          | DCP Package            | `delivery_package`  | dcp, cinema package                                  | Cinema delivery package.                             |
| `qc_report`            | QC Report              | `delivery_package`  | qc report, technical report, exception report        | Report artifact attached to delivery readiness.      |
| `graphics_package`     | Graphics Package       | `supporting_assets` | titles package, graphics export, layered graphics    | Source or rendered graphics assets.                  |
| `archive_turnover`     | Archive / Turnover     | `supporting_assets` | archive, turnover, lto, restore copy                 | Archival or handoff deliverable.                     |

## Quote Line Items

Recommendation: use two layers for quote line items.

- `QuoteLineItemType` enum for base operational behavior
- `quote_line_item_subcategory` reference data for analytics, import mapping, and forecasting defaults

### Primary line type

Use the schema enum for the top-level type and keep it small.

| Canonical key | Preferred label | Synonyms to map from imports and PDFs              | Notes                                                            |
| ------------- | --------------- | -------------------------------------------------- | ---------------------------------------------------------------- |
| `service`     | Service         | service, labor, creative, edit, finishing, package | Default billable work line. Most revenue lines should land here. |
| `expense`     | Expense         | expense, pass through, vendor, travel, courier     | Rebillable or direct cost line.                                  |
| `discount`    | Discount        | discount, rebate, credit                           | Negative commercial reduction to client value.                   |
| `adjustment`  | Adjustment      | adjustment, markup, contingency, tax               | Non-standard positive, neutral, or balancing line.               |

### Line item subcategory

Use subcategories for analysis and mapping. Do not replace the base enum with these values.

Suggested hierarchy:

- `service_labor`
- `service_facility_tech`
- `expense_pass_through`
- `commercial_adjustment`

| Canonical key         | Preferred label       | Parent group            | Synonyms to map from imports and PDFs                | Notes                                                                |
| --------------------- | --------------------- | ----------------------- | ---------------------------------------------------- | -------------------------------------------------------------------- |
| `labor_day`           | Labor Day Rate        | `service_labor`         | day, days, man day, day rate                         | Use when a person or role is billed by day.                          |
| `labor_hour`          | Labor Hour Rate       | `service_labor`         | hour, hours, hr, hourly                              | Use when a person or role is billed by hour.                         |
| `labor_fixed_fee`     | Labor Fixed Fee       | `service_labor`         | fixed fee, flat fee, creative fee                    | Fixed labor or creative charge not tied to units.                    |
| `package_fee`         | Package Fee           | `service_labor`         | package, bundled fee, lot price                      | Bundled scope crossing multiple tasks or sessions.                   |
| `facility_rental`     | Facility Rental       | `service_facility_tech` | suite, room, theatre, bay, stage                     | Booked facility or room charge.                                      |
| `software_license`    | Software / License    | `service_facility_tech` | license, software, subscription, plugin              | Technology or licensed tool charge.                                  |
| `media_storage`       | Media / Storage       | `service_facility_tech` | drive, storage, transfer, cloud, lto                 | Media hardware, storage, archive, or transfer cost.                  |
| `third_party_vendor`  | Third-Party Vendor    | `expense_pass_through`  | vendor, external vendor, pass through, outsource     | External service rebilled to the client.                             |
| `stock_music_license` | Stock / Music License | `expense_pass_through`  | stock, library music, music license, footage license | Rights-cleared content or music cost.                                |
| `travel_expense`      | Travel / Expense      | `expense_pass_through`  | travel, hotel, taxi, per diem, meals                 | Rebillable travel or expense item.                                   |
| `shipping_courier`    | Shipping / Courier    | `expense_pass_through`  | courier, shipping, fedex, messenger                  | Physical shipment or courier cost.                                   |
| `markup`              | Markup                | `commercial_adjustment` | markup, handling, procurement fee                    | Positive commercial adjustment on pass-through costs.                |
| `contingency`         | Contingency           | `commercial_adjustment` | contingency, allowance, reserve                      | Budgeted risk allowance.                                             |
| `discount`            | Discount              | `commercial_adjustment` | discount, rebate, credit, write-off                  | Negative commercial adjustment.                                      |
| `tax`                 | Tax                   | `commercial_adjustment` | vat, sales tax, gst, tax                             | Track separately and exclude from core revenue analytics by default. |

Notes:

- Analytics should use both `lineType` and `lineSubcategory`.
- Keep `unit` as free text for now, but if imports show heavy variation, add a separate controlled `quote_line_item_unit` vocabulary later.

## Project Formats

Recommendation: store canonical project format in `ProjectMetadata.formatType` using controlled reference data instead of open-ended free text.

Use `contentType` and `contentSubtype` only for secondary descriptive axes, not as substitutes for the controlled project format list.

Suggested hierarchy:

- `long_form`
- `series`
- `short_form`
- `other`

| Canonical key         | Preferred label             | Parent group | Synonyms to map from imports and PDFs                      | Notes                                                  |
| --------------------- | --------------------------- | ------------ | ---------------------------------------------------------- | ------------------------------------------------------ |
| `feature_film`        | Feature Film                | `long_form`  | feature, feature film, movie                               | Long-form narrative or stand-alone factual film.       |
| `documentary_feature` | Documentary Feature         | `long_form`  | doc feature, documentary feature                           | Stand-alone documentary film.                          |
| `episodic_series`     | Episodic Series             | `series`     | series, episodic, tv series, serial                        | Multi-episode scripted series.                         |
| `documentary_series`  | Documentary Series          | `series`     | doc series, documentary series                             | Multi-episode factual or documentary series.           |
| `unscripted_series`   | Unscripted / Reality Series | `series`     | reality, entertainment, factual entertainment, competition | Non-scripted episodic programming.                     |
| `commercial`          | Commercial                  | `short_form` | ad, spot, tvc, commercial spot                             | Paid advertising work.                                 |
| `trailer_promo`       | Trailer / Promo             | `short_form` | promo, trailer, teaser, on-air promo                       | Marketing content for another property.                |
| `social_digital`      | Social / Digital            | `short_form` | social, digital, online content, platform content          | Platform-first or social-first short-form work.        |
| `branded_content`     | Branded Content             | `short_form` | branded, branded film, sponsored content                   | Brand-funded editorial content outside pure ads.       |
| `music_video`         | Music Video                 | `short_form` | mv, music video, promo video                               | Music-led short-form project.                          |
| `short_film`          | Short Film                  | `short_form` | short, short film                                          | Narrative or documentary short.                        |
| `corporate_internal`  | Corporate / Internal        | `other`      | internal, corporate, training, sizzle                      | Non-broadcast internal or business communication work. |

## Pipeline Stages

Recommendation: store fine-grained `pipeline_stage` in a reference table and derive or map the coarser `ProjectStatus` enum from it.

Suggested hierarchy:

- `pre_award`
- `delivery`
- `closed`

| Canonical key     | Preferred label | Stage group | Synonyms to map from imports and PDFs           | Maps to `ProjectStatus` |
| ----------------- | --------------- | ----------- | ----------------------------------------------- | ----------------------- |
| `lead`            | Lead            | `pre_award` | lead, enquiry, inquiry, prospect                | `bid`                   |
| `qualified`       | Qualified       | `pre_award` | qualified, scoped, briefed                      | `bid`                   |
| `quoting`         | Quoting         | `pre_award` | estimating, budgeting, quote in progress        | `bid`                   |
| `quote_submitted` | Quote Submitted | `pre_award` | submitted, sent, with client, under review      | `bid`                   |
| `negotiation`     | Negotiation     | `pre_award` | negotiating, revision requested, best and final | `bid`                   |
| `awarded`         | Awarded         | `delivery`  | won, greenlit, awarded                          | `awarded`               |
| `setup`           | Setup           | `delivery`  | onboarding, kickoff, preproduction setup        | `awarded`               |
| `active`          | Active          | `delivery`  | in progress, live, current                      | `active`                |
| `on_hold`         | On Hold         | `delivery`  | hold, paused, awaiting client                   | `active`                |
| `complete`        | Complete        | `delivery`  | complete, delivered, wrapped                    | `complete`              |
| `lost`            | Lost            | `closed`    | lost, not awarded, dead                         | `lost`                  |
| `archived`        | Archived        | `closed`    | archived, closed                                | `archived`              |

Notes:

- Keep the current `ProjectStatus` enum for stable application logic.
- Use `pipeline_stage` for reporting and forecasting nuance inside the broader `bid` and `active` states.
- Keep `ProjectOutcomeType` separate from `pipeline_stage`; outcome records are event history, not the current workflow stage.

## Revenue Categories

Recommendation: use `ReferenceDataValue` category `revenue_category` for quote, forecast, and dashboard slicing. This should be broader than disciplines and more stable than services.

Suggested hierarchy:

- `core_services`
- `pass_through`
- `adjustment`

| Canonical key           | Preferred label         | Parent group    | Synonyms to map from imports and PDFs           | Notes                                                              |
| ----------------------- | ----------------------- | --------------- | ----------------------------------------------- | ------------------------------------------------------------------ |
| `editorial_services`    | Editorial Services      | `core_services` | editorial, offline, edit                        | Revenue for editorial labor and related packages.                  |
| `picture_finishing`     | Picture Finishing       | `core_services` | online, conform, grade, finishing               | Groups picture finishing work for reporting.                       |
| `vfx_graphics`          | VFX / Graphics          | `core_services` | vfx, graphics, titles, comp                     | Combined creative finishing bucket when finer split is not needed. |
| `audio_post`            | Audio Post              | `core_services` | sound, audio, mix, adr, foley                   | Audio editorial and mixing revenue.                                |
| `localization`          | Localization            | `core_services` | subtitles, captions, localisation, version text | Language and territory adaptation revenue.                         |
| `delivery_versioning`   | Delivery / Versioning   | `core_services` | delivery, versioning, mastering, imf, dcp       | Final packaging and output revenue.                                |
| `post_management`       | Post Management         | `core_services` | producing, supervision, coordination            | Commercial value of project management and oversight.              |
| `technology_facilities` | Technology / Facilities | `core_services` | suite, room, storage, software, theatre         | Facility and technical usage billed as revenue.                    |
| `third_party_rebill`    | Third-Party Rebill      | `pass_through`  | pass through, vendor rebill, external cost      | External supplier costs rebilled to the client.                    |
| `expenses_rebill`       | Expenses Rebill         | `pass_through`  | travel, courier, expenses                       | Non-vendor pass-through items rebilled to the client.              |
| `discount_adjustment`   | Discount / Adjustment   | `adjustment`    | discount, rebate, credit                        | Negative adjustment bucket for net-revenue reporting.              |
| `tax_non_revenue`       | Tax                     | `adjustment`    | vat, tax, sales tax, gst                        | Keep separate from revenue analytics.                              |

## Counterparties

Recommendation: align with the current `Company`, `CompanyClassification`, and `ProjectParty` schema.

Use enums for the core roles already present in the system design, and use softer reference-data tags only when the business needs extra labels beyond those core roles.

Suggested hierarchy:

- `commercial`
- `supply`

### Company classifications

Use for durable attributes on the company itself.

| Canonical key        | Preferred label    | Parent group | Synonyms to map from imports and PDFs     | Notes                                                         |
| -------------------- | ------------------ | ------------ | ----------------------------------------- | ------------------------------------------------------------- |
| `client`             | Client             | `commercial` | client, customer, commissioner            | Primary commercial customer in Quotes4.                       |
| `production_company` | Production Company | `commercial` | prodco, production co, production company | Company producing the work on behalf of the client or studio. |
| `studio`             | Studio             | `commercial` | studio, distributor, rights owner         | Studio or rights-owning commercial counterparty.              |
| `streamer`           | Streamer           | `commercial` | streamer, svod, avod platform             | Streaming platform associated with commissioning or delivery. |
| `broadcaster`        | Broadcaster        | `commercial` | broadcaster, network, channel             | Broadcast network or channel.                                 |
| `competitor`         | Competitor         | `commercial` | competitor, competing vendor              | Company that won or is competing for the work.                |
| `vendor`             | Vendor             | `supply`     | supplier, facility, partner vendor        | External supplier to Quotes4's business.                      |

### Project party roles

Use for the role a company plays on a specific project.

| Canonical key        | Preferred label    | Parent group | Synonyms to map from imports and PDFs     | Notes                                                                    |
| -------------------- | ------------------ | ------------ | ----------------------------------------- | ------------------------------------------------------------------------ |
| `client`             | Client             | `commercial` | client, customer, commissioner            | Primary client party on a project.                                       |
| `production_company` | Production Company | `commercial` | prodco, production co, production company | Production company tied to the project.                                  |
| `studio`             | Studio             | `commercial` | studio, distributor                       | Studio role on the project.                                              |
| `streamer`           | Streamer           | `commercial` | streamer, platform                        | Streaming platform role on the project.                                  |
| `broadcaster`        | Broadcaster        | `commercial` | broadcaster, network, channel             | Broadcaster role on the project.                                         |
| `competitor`         | Competitor         | `commercial` | competitor, awarded elsewhere             | Used when a competing company won or is tracked against the opportunity. |

Notes:

- A single company may hold multiple roles across projects.
- Company classification and project party role should remain separate concepts.
- If the business later needs softer tags such as `agency` or `brand`, add them as reference-data tags first rather than replacing the core enums.

## Actuals Mapping Categories

Recommendation: use `ReferenceDataValue` category `actuals_mapping_category` during CETA import review.

Keep this separate from discipline so actuals can be analyzed both by spend nature and by mapped discipline.

Current schema note:

- The current schema maps actuals to project and discipline, but not yet to a controlled spend category.
- Add an `actuals_mapping_category_key` or relation on `ActualMappingDecision` and `MappedActual` before relying on spend-nature reporting.

Suggested hierarchy:

- `labor`
- `facility_tech`
- `external`
- `expense`
- `adjustment`
- `exception`

| Canonical key         | Preferred label         | Parent group    | Synonyms to map from imports and PDFs        | Notes                                                             |
| --------------------- | ----------------------- | --------------- | -------------------------------------------- | ----------------------------------------------------------------- |
| `internal_labor`      | Internal Labor          | `labor`         | payroll, staff cost, salary cost             | Spend attributable to internal employees.                         |
| `freelance_labor`     | Freelance Labor         | `labor`         | freelance, contractor, day player            | External individual labor not treated as a larger vendor service. |
| `facility_tech`       | Facility / Tech         | `facility_tech` | suite, room, storage, software, machine room | Operational facility and technology costs.                        |
| `media_storage`       | Media / Storage         | `facility_tech` | drive, lto, storage, transfer, cloud         | Media handling and storage spend.                                 |
| `external_vendor`     | External Vendor Service | `external`      | vendor, outsource, po, external service      | Third-party company service cost.                                 |
| `localization_vendor` | Localization Vendor     | `external`      | subtitles vendor, caption vendor, dub vendor | Localization spend separated for reporting clarity.               |
| `licensing`           | Licensing               | `external`      | stock, music license, footage license        | Rights-based third-party spend.                                   |
| `travel_expense`      | Travel / Expense        | `expense`       | travel, hotel, taxi, meals, per diem         | Reimbursable or operational travel spend.                         |
| `shipping_courier`    | Shipping / Courier      | `expense`       | courier, fedex, shipping, messenger          | Shipment or messenger costs.                                      |
| `tax_fee`             | Tax / Fee               | `adjustment`    | vat, tax, fee, levy                          | Taxes and statutory or platform fees.                             |
| `adjustment_credit`   | Adjustment / Credit     | `adjustment`    | credit, correction, reversal, write-off      | Corrections that should not be treated as normal spend.           |
| `unmapped_review`     | Unmapped Review         | `exception`     | suspense, unknown, uncoded                   | Explicit bucket for rows that still need human review.            |

## Forecast Allocation Methods

Recommendation: keep as enum because the set is small and directly drives allocation logic.

| Canonical key | Preferred label           | Synonyms to map from imports and PDFs                            | Notes                                                                  |
| ------------- | ------------------------- | ---------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `schedule`    | Schedule-Based Allocation | schedule driven, by schedule, phased by dates, pro rata by dates | Allocates forecast amount across months using schedule dates.          |
| `manual`      | Manual Monthly Allocation | manual split, manual phasing, user entered, override             | Explicit user-entered monthly values that must sum to expected amount. |

Notes:

- Do not introduce `hybrid` as a separate canonical value in MVP.
- If a forecast starts from a schedule but is overridden by hand, store it as `manual` and preserve the rationale in notes or audit history.

## Common Status Fields

Recommendation: use enums for stable workflow states, booleans for activation flags, and timestamp fields for milestones.

### Status field standards

| Field                            | Canonical values                                                                   | Preferred labels                                                     | Synonyms to map                                                                 | Recommendation                                                                  |
| -------------------------------- | ---------------------------------------------------------------------------------- | -------------------------------------------------------------------- | ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| `project_status`                 | `bid`, `awarded`, `lost`, `active`, `complete`, `archived`                         | Bid, Awarded, Lost, Active, Complete, Archived                       | won -> `awarded`; in progress/live -> `active`; delivered/wrapped -> `complete` | Enum, already present in schema.                                                |
| `project_outcome_type`           | `bid`, `awarded`, `lost`                                                           | Bid, Awarded, Lost                                                   | won -> `awarded`; no bid -> `lost` only if it is truly a lost opportunity event | Enum, already present in schema and should remain separate from current status. |
| `quote_version_status`           | `draft`, `issued`, `superseded`, `accepted`, `rejected`                            | Draft, Issued, Superseded, Accepted, Rejected                        | sent/submitted -> `issued`; approved -> `accepted`; declined -> `rejected`      | Enum, already present in schema.                                                |
| `pdf_extraction_run_status`      | `queued`, `processing`, `extracted`, `in_review`, `approved`, `rejected`, `failed` | Queued, Processing, Extracted, In Review, Approved, Rejected, Failed | pending -> `queued`; parsing/ocr -> `processing`; review -> `in_review`         | Enum, already present in schema.                                                |
| `extraction_review_status`       | `pending`, `approved`, `rejected`                                                  | Pending, Approved, Rejected                                          | todo -> `pending`; accepted -> `approved`                                       | Enum, already present in schema for extracted fields and line items.            |
| `ceta_import_status`             | `uploaded`, `parsed`, `in_review`, `approved`, `rejected`, `failed`                | Uploaded, Parsed, In Review, Approved, Rejected, Failed              | staged -> `uploaded`; reviewed -> `in_review`; posted -> `approved`             | Enum, already present in schema.                                                |
| `ceta_row_status`                | `unmatched`, `suggested`, `mapped`, `approved`, `rejected`                         | Unmatched, Suggested, Mapped, Approved, Rejected                     | auto-match -> `suggested`; matched -> `mapped`; confirmed -> `approved`         | Enum, already present in schema.                                                |
| `actual_mapping_decision_status` | `suggested`, `approved`, `rejected`                                                | Suggested, Approved, Rejected                                        | proposed -> `suggested`; accepted -> `approved`                                 | Enum, already present in schema.                                                |
| `mapping_method`                 | `manual`, `suggested`, `rule`                                                      | Manual, Suggested, Rule                                              | auto -> `suggested`; rules engine -> `rule`                                     | Enum, already present in schema and should not be overloaded as a status.       |
| `forecast_version_status`        | `draft`, `submitted`, `locked`, `superseded`                                       | Draft, Submitted, Locked, Superseded                                 | final/frozen -> `locked`; replaced -> `superseded`                              | Enum, already present in schema.                                                |
| `is_active`                      | `true`, `false`                                                                    | Active, Inactive                                                     | enabled/disabled                                                                | Boolean, for reference data and counterparties.                                 |

### Status naming guidelines

- Use `status` for the primary lifecycle field on a record.
- Use `reviewStatus` with `ExtractionReviewStatus` values for individual extracted fields and line items.
- Use `decisionStatus` for mapping approvals and `mappingMethod` for how the mapping was produced.
- Use `is_active` for reference-data availability, not commercial lifecycle.
- Prefer milestone timestamps such as `issued_at`, `approved_at`, `locked_at`, and `archived_at` for auditability instead of adding extra status values.

## Implementation Notes for Codex

- Seed these vocabularies in reference data before building ingestion automation.
- Where possible, seed through `reference_data_values` categories first and promote a family to a dedicated table only when it gains strong relationships or bespoke fields.
- Keep raw source strings in import staging tables even after mapping.
- Log who approved a mapping and when when a source term is normalized to a canonical key.
- Use canonical keys in analytics, dashboards, forecast logic, and comparable-project features.
- Store canonical project format in `ProjectMetadata.formatType` and preserve raw imported values in ingestion tables or metadata.
- Use preferred labels in UI tables, forms, exports, and review screens.
- When uncertain during import, map to an explicit review bucket like `unmapped_review` rather than silently guessing.
