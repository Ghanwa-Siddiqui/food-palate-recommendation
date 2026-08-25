# Chaska Food Palate Recommendation System

Chaska's Data Layer & Backend Core is a modular FastAPI service for restaurant, dish, and deal catalog data. This foundation is designed for Supabase-hosted PostgreSQL and its pgvector extension without contacting Supabase during application import.

All sample restaurants are synthetic development data, not verified real businesses.

## Architecture

- `backend/app/models`: SQLAlchemy 2 ORM entities with UUID identifiers
- `backend/app/schemas`: Pydantic API schemas and pagination envelopes
- `backend/app/repositories`: database-only query and filter logic
- `backend/app/services/data_core`: catalog business logic and replaceable embeddings
- `backend/app/api/routes`: thin FastAPI route handlers
- `backend/migrations`: Alembic setup and initial pgvector-compatible schema
- `backend/scripts`: guarded, idempotent development seed command
- `docs/contracts/v1`: versioned JSON Schema contracts
- `data/seed`: sample dataset documentation

Database engine and embedding model construction are lazy. Importing `app.main` neither opens a database connection nor loads/downloads a sentence-transformer model.

The versioned `user-taste.schema.json` contract provides a storage-neutral handoff for
onboarding preferences: cuisines, favourite dishes, five taste preferences, textures,
budget bounds, dietary requirements, allergies, disliked ingredients, a taste-vector
slot, and update time. No user-taste table, endpoint, vector-generation algorithm, EMA
update, or similarity logic is implemented here; those remain owned by the onboarding
and personalization module.

Storage-neutral `review-summary.schema.json` and `interaction.schema.json` contracts
also preserve the agreed cross-module shapes without implementing sentiment analysis,
review aggregation, feedback processing, or recommendation behaviour.

## Installation

Python 3.11 or later is required.

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
```

Install local embedding support only when needed:

```powershell
python -m pip install -e ".[embedding]"
```

## Environment

Copy `.env.example` to a local `.env` and replace placeholders locally. Never commit a real `.env` or credentials.

Supabase's Transaction Pooler connection string should be expressed as a SQLAlchemy psycopg URL and retain SSL:

```text
DATABASE_URL=postgresql+psycopg://postgres.PROJECT_REF:PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres?sslmode=require
```

Percent-encode special characters in passwords. For deployed workloads, tune the small application pool to fit Supabase connection limits.

## Run locally

From `backend`:

```powershell
uvicorn app.main:app --reload
```

OpenAPI documentation is at `http://127.0.0.1:8000/docs`.

## API summary

- `GET /health`
- `GET /restaurants` and `GET /restaurants/{restaurant_id}`
- `GET /restaurants/{restaurant_id}/dishes`
- `GET /dishes` and `GET /dishes/{dish_id}`
- `GET /dishes/{dish_id}/vector` (the only endpoint exposing embeddings)
- `GET /deals` and `GET /deals/{deal_id}`

List endpoints support pagination. Catalog filters cover city, cuisine, halal status, restaurant, dish-name search, and price bounds as applicable.

Public restaurant and dish responses use `lat` and `lng` for coordinates. Prices,
coordinates, discounts, and other contract fields declared as JSON numbers are emitted
as numbers rather than strings; internal database columns may retain descriptive names.

## Tests

Tests use an isolated in-memory SQLite database, fake repositories, and a deterministic fake embedding provider. They do not contact Supabase or download a model.

```powershell
cd backend
pytest
ruff check .
```

## Supabase migration

Do not run migrations until a reviewed Supabase `DATABASE_URL` is configured. Then, from `backend`:

```powershell
alembic current
alembic upgrade head
```

The initial migration uses `CREATE EXTENSION IF NOT EXISTS vector` and creates the six owned tables. The downgrade intentionally leaves the shared extension installed.

## Development seed data

Run only against an explicitly configured local development database after applying migrations:

```powershell
python -m scripts.seed --confirm-development-data
```

The script creates 30 deterministic sample restaurants, 90 dishes, and 30 deals. It is
idempotent and runs only when `APP_ENV` is `development` or `test`, the confirmation flag
is present, and the database is local SQLite or PostgreSQL on a loopback host. Every
remote database—including Supabase—is rejected. It omits vectors by default;
`--with-embeddings` lazily loads the configured model when local embedding dependencies
are installed. Dish embeddings have one authoritative dimension of 384.

### Explicit Chaska development Supabase seed

Remote seeding remains disabled by default. Before using the one-time development mode,
configure `APP_ENV=development`, `DATABASE_URL`, and `EXPECTED_SUPABASE_PROJECT_REF` in
the ignored local `.env`. The expected project reference must exactly match the project
reference extracted from the configured Supabase connection URL. Do not place credentials
or a real project reference in tracked files.

From `backend`, manually run exactly:

```powershell
python -m scripts.seed --confirm-development-data --allow-remote-development --remote-confirmation SEED_CHASKA_DEVELOPMENT
```

This command does not generate embeddings. Before inserting anything it verifies that the
database is at the current Alembic head, all six owned tables exist, and `restaurants`,
`dishes`, and `deals` are empty. It aborts if any catalog data exists. A successful run
adds only 30 restaurants, 90 dishes, and 30 deals; it never seeds users, reviews, or
interactions. Re-running it against the populated remote catalog safely aborts without a
reset or deletion.

### Correct an already-seeded development catalog

For a development database seeded before BBQ was classified as a preparation style, set
`APP_ENV=development`, `DATABASE_URL`, and `EXPECTED_SUPABASE_PROJECT_REF` for the intended
Supabase project, then run this command manually from `backend`:

```powershell
python -m scripts.correct_bbq_cuisine --confirmation CORRECT_CHASKA_BBQ_CUISINE
```

The command verifies the Supabase project reference, Alembic head, required tables, four
deterministic restaurant IDs, twelve deterministic dish IDs, and their relationships before
making changes. It updates all records in one transaction, aborts on partial or unexpected
data, and reports without writing when the correction has already been applied.

## Ownership boundary

### Shared location contract notice

Restaurant `lat` and `lng` are nullable as of migration `20260826_0002`. They are always
populated together or returned together as `null`. Consumers owned by Esha must treat
`location_verified=false` as unavailable for distance filtering or ranking; these records
remain valid catalog/search results. `coordinates_source_url` and
`coordinates_verified_at` provide optional audit metadata.

This module owns the data layer, data-core services, restaurant/dish/deal routes, migrations, seed data, contracts, and related tests. It deliberately excludes Review Intelligence, personalization, ranking, collaborative filtering, sentiment extraction, feed UI, and full frontend work. See `AGENTS.md` before editing shared areas.
