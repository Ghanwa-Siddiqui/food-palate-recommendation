# Ranking feed

The Data Core FastAPI application exposes `GET /ranking/feed/{user_id}`. The path user
must exist in the backend `users` table. Candidates come from the real dish and
restaurant ORM models; review averages and interaction counts are aggregated from the
existing Review Intelligence-compatible tables.

The endpoint accepts optional validated query preferences for budget, dietary tags,
allergies, disliked ingredients, halal requirement, coordinates, maximum distance, a
384-value taste vector, and result limit. `halal` is not treated as a dish dietary tag:
`require_halal=true` checks the restaurant's catalog halal status. Unavailable dishes
are always excluded. Missing or unverified restaurant coordinates neither exclude nor
penalize a candidate unless a verified pair is present.

## Signals and defaults

The deterministic composite uses independently named signals:

- taste alignment: 45%
- review average: 15%
- observed interaction popularity: 10%
- verified distance: 10%
- price within the supplied budget: 10%
- context: 5%
- collaborative: 5%

An unavailable signal receives an explicit neutral score of 50. The response lists
which signals were neutral. Context and collaborative inputs have no integrated data
provider on this branch, so they remain neutral rather than being fabricated. Taste is
neutral when either the request taste vector or dish embedding is absent. Review and
popularity are neutral when there are no observations.

The endpoint does not generate embeddings or contact external services. Equal totals
are ordered by case-insensitive dish name and then dish UUID for stable results.

## Jinja feed integration

The runnable root FastAPI/Jinja application exposes `/app/feed`. It calls the Ranking
API over HTTP; configure its origin with `RANKING_API_BASE_URL` (default
`http://127.0.0.1:8001`) and its request timeout with
`RANKING_API_TIMEOUT_SECONDS` (default `3`). Run the backend and root applications on
different ports.

The screen accepts a UUID from the existing onboarding flow and optional budget,
dietary, and halal filters. It renders loading, success, empty, invalid-filter,
missing-user, unavailable-data, and backend-failure states. The UI only displays the
ranked response; it contains no scoring implementation. Because the Ranking API does
not publish dish image URLs, result cards use a local visual placeholder and never
invent a remote image URL.

The orphan React mock files were removed after this Jinja integration replaced their
feed-screen purpose. The repository has no React package manifest, entry point, or
build pipeline.
