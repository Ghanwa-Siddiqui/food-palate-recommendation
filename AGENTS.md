# Chaska ownership boundaries

This repository is maintained by multiple contributors. Keep changes modular and merge-safe.

## Data Layer & Backend Core (Ghanwa)

Owned paths:

- `backend/app/db`
- `backend/app/models`
- `backend/app/schemas`
- `backend/app/repositories`
- `backend/app/services/data_core`
- `backend/app/api/routes/restaurants.py`
- `backend/app/api/routes/dishes.py`
- `backend/app/api/routes/deals.py`
- `backend/scripts`
- `backend/migrations`
- `data/seed`
- data-related tests and dish/restaurant contracts

Do not add Review Intelligence, personalization, ranking, collaborative filtering, review sentiment, feed UI, or a full frontend here. Preserve public contracts and coordinate before changing another contributor's module. Never commit credentials or a real `.env`. Database operations must use `DATABASE_URL`; imports must not connect to external services.

`docs/contracts/v1/user-taste.schema.json` is a storage-neutral integration contract only.
Manahil owns onboarding UI, preference collection, user taste-vector storage/generation,
EMA feedback updates, and user-similarity logic. Do not add a user-taste ORM model,
migration, API endpoint, or personalization service without explicit team agreement.
