# Chaska / Namak

Namak is Chaska's food-palate web experience. It combines a server-rendered FastAPI/Jinja UI with persisted Data Core records, Review Intelligence summaries, Personalization profiles/interactions, and a deterministic Ranking API.

## Architecture

Two separate Python processes avoid the ambiguous `app` package names:

- `backend/app` on port 8000: SQLAlchemy/PostgreSQL data, catalog APIs, review summaries, user profiles/interactions, and ranking.
- root `app` on port 8001: Supabase Auth, signed HTTP-only sessions, CSRF-protected forms, backend client, and responsive Jinja screens.
- `review_intelligence`: extraction/aggregation tools; structured results persist on reviews and are exposed by the backend review-summary API.

The UI never duplicates ranking logic or connects directly to the database. Private backend calls carry the authenticated user ID and optional shared `CHASKA_INTERNAL_API_KEY`; ownership checks reject cross-user access when that key is configured.

Phase 1 restaurant partners select their account type at signup, complete a restaurant profile at `/partner/onboarding`, and manage only their owned restaurants from `/partner/dashboard`. Roles are `customer`, `restaurant_partner`, and `admin`; the admin role is represented without an admin dashboard. Dish management is intentionally deferred.

## User journey

Routes cover landing, signup, login, four-step onboarding, ranked feed, restaurant/menu, dish detail, saved dishes, profile/activity, preference editing, logout, and expired-session recovery. Onboarding stores a 384-dimensional taste vector. Click/save/order-interest actions use the interaction contract; save is idempotent and feedback updates the vector with EMA when a dish embedding exists. Missing coordinates, embeddings, reviews, deals, similarities, and images remain explicit unavailable/neutral states.

Ranking uses the workbook weights exactly: taste 45%, food/profile 20%, reviews 10%, distance 10%, price 10%, and popularity 5%. Missing signals score a documented neutral 50 and are returned as `neutral_signals`.

Generated local WebP assets in `app/static/images` provide honest cuisine-level fallbacks (Pakistani, pan-Asian, and Western/Mediterranean), plus restaurant and landing imagery. Nothing is hotlinked.

## Configuration

Copy `.env.example` locally and fill placeholders. Never commit the real `.env`.

The backend requires `DATABASE_URL`. Auth requires `SUPABASE_URL` and the public/anon `SUPABASE_PUBLISHABLE_KEY`—never a service-role key. Set a random 32+ character `SESSION_SECRET`; set `SESSION_COOKIE_SECURE=true` behind HTTPS. Set the same optional `CHASKA_INTERNAL_API_KEY` for both processes. `BACKEND_API_BASE_URL` defaults to `http://127.0.0.1:8000`.

## Install and run

Use separate environments:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -e "backend[test]"
```

The launcher reads the ignored root `.env` into its own process before validation. Values
already defined in the process environment take priority. It does not echo configuration
values and never creates, seeds, or migrates a database.

Start both services:

```powershell
.\scripts\run_dev.ps1
```

Backend and UI output is written to the ignored `.dev-logs` directory as separate
`*.stdout.log` and `*.stderr.log` files. The launcher prints only that directory path.
If either service exits early, the launcher reports which error log to inspect and stops
both Uvicorn process trees. Pressing Ctrl+C also stops the reload parents and children.

Validate configuration and virtual environments without starting either service:

```powershell
.\scripts\run_dev.ps1 -ValidateOnly
```

Manual startup:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --reload
cd ..
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8001 --reload
```

## Production deployment

Deploy the API to Railway with the service root directory set to `backend/`. The checked-in
`backend/railway.json` uses this start command and never runs migrations or seeds:

```text
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Configure Railway with `DATABASE_URL`, `APP_ENV=production`,
`CHASKA_INTERNAL_API_KEY`, `EXPECTED_SUPABASE_PROJECT_REF`, and
`EMBEDDING_DIMENSION=384`. Railway checks the public `/health` endpoint. All other backend
requests require the shared internal key. Apply reviewed migrations separately as an explicit
release operation; startup deliberately does not alter the database.

Deploy the repository root to Vercel. `api/index.py` is the Python ASGI entrypoint and
`vercel.json` bundles the existing `app/templates` and `app/static` assets, preserving the
server-rendered Jinja application. Configure Vercel with `SUPABASE_URL`,
`SUPABASE_PUBLISHABLE_KEY`, a random 32+ character `SESSION_SECRET`,
`SESSION_COOKIE_SECURE=true`, the Railway public HTTPS `BACKEND_API_BASE_URL`,
`BACKEND_API_TIMEOUT_SECONDS=30`, the same `CHASKA_INTERNAL_API_KEY`, and
`APP_ENV=production`.

Production startup fails closed when required values are absent. The UI also rejects localhost,
loopback, and non-HTTPS backend URLs. Session cookies remain signed, HTTP-only, SameSite=Lax,
and Secure on Vercel. Configuration errors name only missing or unsafe variable names; secret
values are never logged.

After review, apply the forward-only migration manually with `cd backend; .\.venv\Scripts\alembic.exe upgrade head`. The launcher never runs migrations or seeds.

## Validation

Tests use SQLite, fake Supabase Auth, fake clients/repositories, deterministic embeddings, and local images. They do not contact Supabase or external services.

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests --basetemp=.pytest-work/root
cd backend
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff format --check app tests
.\.venv\Scripts\python.exe -m ruff check app tests
```

Run Review Intelligence tests from the repository root with its dependencies from `review_intelligence/requirements.txt` so package imports resolve correctly.
