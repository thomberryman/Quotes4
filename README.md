# Quotes4

Quotes4 is a multi-user quoting, forecasting, and actuals analysis platform for post production teams. The current scaffold establishes the MVP runtime shape: a FastAPI backend, a Python worker, a Next.js frontend, shared API contracts, and PostgreSQL-backed operational workflows.

## Stack

- `apps/web`: Next.js business UI
- `apps/api`: FastAPI modular monolith API
- `apps/worker`: Python background worker for ingestion, parsing, and recalculation
- `packages/contracts`: OpenAPI-driven TypeScript client boundary
- `packages/domain`: shared business rules and types
- `packages/db`: legacy Prisma reference retained in-repo but not used for active schema ownership
- PostgreSQL for the shared system of record
- S3-compatible object storage for quotes, imports, and attachments
- PostgreSQL-backed job queue for async work

## Getting Started

1. Copy `.env.example` to `.env`.
2. Install workspace dependencies with `npm install`.
3. Install Python app dependencies with `npm run deps:python`.
4. Start local infrastructure with `docker compose up -d postgres minio mailpit`.
5. Export the OpenAPI contract with `npm run contracts:generate`.
6. Run database migrations with `npm run db:migrate`.
7. Seed local reference and auth data with `npm run db:seed`.
8. Start the web app with `npm run dev:web`.
9. Start the API with `npm run dev:api`.
10. Start the worker with `npm run dev:worker`.

To run the entire stack in containers instead, use `docker compose up --build`.

`.env.example` is now a demo-oriented local configuration: it points at a demo database, uses demo cookie names, and seeds the full sample dataset.

## Demo And Live Side By Side

Use the checked-in Compose env files to keep a seeded demo stack and a live-import stack running at the same time on one machine.

### Demo Stack

1. Start the services with `docker compose --env-file compose.demo.env -p quotes4-demo up -d --build`.
2. Run migrations with `docker compose --env-file compose.demo.env -p quotes4-demo run --rm api alembic upgrade head`.
3. Seed demo data with `docker compose --env-file compose.demo.env -p quotes4-demo run --rm api python -m app.seed --mode demo`.
4. Open the app at [http://localhost:3000](http://localhost:3000).

### Live Import Stack

1. Start the services with `docker compose --env-file compose.live.env -p quotes4-live up -d --build`.
2. Run migrations with `docker compose --env-file compose.live.env -p quotes4-live run --rm api alembic upgrade head`.
3. Seed baseline access and reference data with `docker compose --env-file compose.live.env -p quotes4-live run --rm api python -m app.seed --mode baseline`.
4. Open the app at [http://localhost:3010](http://localhost:3010).

The two stacks use separate PostgreSQL containers, storage namespaces, host ports, and auth cookie names, so you can stay logged into both at once on `localhost`.

If you prefer running outside Docker, use `npm run db:seed:demo` for the demo database and `npm run db:seed:baseline` for the live-import database after switching `DATABASE_URL` and the related environment variables.

## Commands

- Build: `npm run build`
- Install Python deps: `npm run deps:python`
- Run DB migrations: `npm run db:migrate`
- Seed DB: `npm run db:seed`
- Seed demo DB explicitly: `npm run db:seed:demo`
- Seed baseline/live DB explicitly: `npm run db:seed:baseline`
- Generate contracts: `npm run contracts:generate`
- Lint: `npm run lint`
- Typecheck: `npm run typecheck`
- Test: `npm run test`

`apps/api` owns the active database schema and migration path through SQLAlchemy and Alembic. The Prisma package under `packages/db` remains available only as a legacy reference and is not part of the default runtime verification flow.

## Key Documents

- Product requirements: [docs/PRD.md](/Users/thoberry/Desktop/CODEX/Quotes4/docs/PRD.md)
- Architecture: [docs/architecture.md](/Users/thoberry/Desktop/CODEX/Quotes4/docs/architecture.md)
- Database design: [docs/database-design.md](/Users/thoberry/Desktop/CODEX/Quotes4/docs/database-design.md)
- Implementation tracker: [PLANS.md](/Users/thoberry/Desktop/CODEX/Quotes4/PLANS.md)
