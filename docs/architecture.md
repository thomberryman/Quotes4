# Architecture Recommendation

## Overview

The Quotes4 MVP uses a polyglot monorepo with a FastAPI modular monolith, a separate Python worker, and a Next.js business UI. This keeps business rules close to the database, preserves auditability, and gives the frontend and future mobile clients one shared public API surface.

## Components

- `apps/web`: responsive Next.js user interface optimized for desktop workflows with mobile-ready layouts
- `apps/api`: FastAPI REST API that owns auth, projects, quotes, imports, forecasts, dashboards, files, and audit behaviors
- `apps/worker`: Python async job runner for ingestion, parsing, reconciliation, and long-running background tasks
- `packages/contracts`: generated TypeScript API client and shared OpenAPI artifacts
- `packages/domain`: shared types, enums, forecasting utilities, and explainable comparables logic

## Data Stores

- PostgreSQL as the single shared system of record
- S3-compatible object storage for PDFs and uploaded files
- PostgreSQL-backed job queue via the `background_jobs` table and worker polling

## Architectural Principles

- Single company, shared-database deployment
- Invite-only work-email authentication with app-managed RBAC
- Immutable financial history for versioning, imports, and audit
- Explainable business rules over opaque automation
- Desktop-first workflows with responsive UI behavior
- Direct browser uploads via presigned object-storage intents
- Contract-first API reuse across web and future mobile clients

## Public Module Boundaries

- `auth`
- `reference-data`
- `clients`
- `projects`
- `quotes`
- `quote-ingestion`
- `actuals-imports`
- `forecasts`
- `dashboards`
- `files`
- `audit`
- `jobs`

## Deployment Shape

- Docker-based local development with `web`, `api`, `worker`, `postgres`, `minio`, and `mailpit`
- Web, API, and worker deployed as separate processes
- PostgreSQL and object storage as managed or containerized infrastructure
- CI runs lint, typecheck, tests, and build validation
