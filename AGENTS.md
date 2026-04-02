# AGENTS.md

## Purpose

This repository is for a multi-user post production quoting, forecasting, and actuals analysis platform.

Prioritize operational clarity, maintainability, auditability, and explainable business logic over clever or opaque solutions.


## Product Scope

The system must support:

- quote creation and versioning
- client and project history
- PDF quote ingestion with review
- CETA import and reconciliation
- monthly forecasting
- bid, awarded, and lost tracking
- comparable-project recommendations
- embedded dashboards

## Working Rules

- Always start by producing a plan before making code changes.
- Plan first for non-trivial work.
- If a task affects multiple modules or is likely to take a while, create or update `PLANS.md` before coding.
- Prefer practical, maintainable solutions over clever ones.
- Preserve auditability and explainability in data flows and decision logic.
- Treat `apps/api` as the active schema and migration owner. Legacy Prisma artifacts under `packages/db` are reference-only unless a task explicitly says otherwise.
- Run relevant tests and checks after major changes.
- In handoff notes, summarize what changed, what was tested, and any remaining risks.

## Domain Rules

- Forecasting must support both schedule-based allocation and manual monthly allocation.
- Bid, awarded, and lost work must be tracked separately.
- Quote version history must be preserved.
- Imported actuals must remain traceable to source imports.
- Comparable-project recommendations must be explainable and reviewable, not black-box.

## UI Rules

- Prioritize clarity over decoration.
- Treat this as an operational business system, not a marketing site.
- Favor obvious labels, stable workflows, and readable tables/forms over visual flourish.

## Expected Repo Layout

Use or evolve a structure like this as the codebase grows:

```text
/app or /src            # application code
/components             # shared UI components
/features               # domain feature modules
/lib                    # shared utilities and services
/data or /db            # schemas, migrations, seeds, import logic
/tests                  # automated tests
/docs                   # product, technical, and workflow docs
/scripts                # developer and operational scripts
/PLANS.md               # active implementation plans for larger tasks
```

## Build, Test, Lint

- Build: `npm run build`
- Test: `npm run test`
- Lint: `npm run lint`
