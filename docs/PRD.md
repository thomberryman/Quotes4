# Product Requirements Document

## Product Summary

Quotes4 is an internal operational system for post production sales and operations teams. It centralizes quote management, project history, actuals reconciliation, forecasting, and historical learning into one shared application and one shared database.

## Problem Statement

Critical commercial and operational data is spread across PDFs, spreadsheets, email, and CETA exports. That fragmentation creates slow quote turnaround, inconsistent forecasting, weak reporting, and poor auditability.

## Goals

- Build and version quotes in one shared system
- Compare quote, forecast, and actuals at project and discipline level
- Forecast revenue monthly using either schedules or manual allocations
- Track bid, awarded, lost, active, and complete work clearly
- Ingest quote PDFs and CETA data with reviewable human checkpoints
- Surface explainable historical comparisons to guide new bids

## Non-Goals

- Native mobile application
- External client portal in MVP
- Fully automated quote ingestion without review
- Black-box recommendation engine
- Full ERP or accounting-system replacement

## Users

- System Admin
- Sales / Estimator
- Post Producer / Post Supervisor
- Finance / Analyst
- Leadership / Read Only

## Core Workflows

### Quote Lifecycle

Create a project, add counterparties and staffing assumptions, build quote sections and line items, save drafts, issue immutable versions, and export a client-ready PDF.

### Forecasting

Maintain project-level and discipline-level forecasts using either schedule-derived allocations or manual month allocations. Compare forecast against actuals over time.

### Import and Reconciliation

Upload quote PDFs or CETA exports into immutable staging areas, review and map extracted data, resolve mismatches, then approve into operational records.

### Historical Learning

Review similar prior work with visible reasons for similarity across client, content type, budget range, duration, and crew mix.

## Success Metrics

- Shorter quote preparation time
- Faster monthly forecast updates
- Higher actuals reconciliation coverage
- Full traceability from imported source rows to approved records
- Reduced dependence on ad hoc spreadsheets

