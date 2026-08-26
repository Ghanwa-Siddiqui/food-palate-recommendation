# Personalization Engine — API Contracts

Owner: Manahil · Module: `feature/personalization-manahil`

This is the surface the **Ranking Engine (Esha)** and **Feed UI (Esha)** call.
Interaction events also flow back in here from the feed.

`UserTaste` and `Interaction` conform field-for-field to Ganva's published
`docs/contracts/v1/user-taste.schema.json` and `interaction.schema.json`
(on `feature/data-core-ghanwa`) — those are the source of truth if this
doc and that schema ever drift; file an issue rather than picking one.

Base URL: `/api`

---

## Data shapes

### `UserTaste`
The full user profile stored server-side and returned by the taste-vector endpoint.

```json
{
  "user_id": "3f9a1e2b-...-uuid",
  "preferred_cuisines": ["Pakistani", "Italian"],
  "favourite_dishes": ["biryani", "pasta"],
  "spice_preference": 3,
  "sweetness_preference": 2,
  "sourness_preference": 2,
  "saltiness_preference": 2,
  "oiliness_preference": 2,
  "preferred_textures": ["tender", "crispy"],
  "budget_min": 500,
  "budget_max": 1500,
  "dietary_requirements": ["halal"],
  "allergies": [],
  "disliked_ingredients": [],
  "taste_vector": [0.031, -0.114, 0.087, "…384 floats total"],
  "last_updated": "2026-08-26T10:14:22.913+00:00"
}
```

| Field                    | Type              | Notes                                          |
|--------------------------|-------------------|-------------------------------------------------|
| `user_id`                | string (uuid)     |                                                   |
| `preferred_cuisines`     | string[]          |                                                   |
| `favourite_dishes`       | string[]          | Free-text dish names                             |
| `spice_preference`       | int (0–5)         | matches dish `spice_level` scale                 |
| `sweetness_preference`   | int (0–5)         |                                                   |
| `sourness_preference`    | int (0–5)         |                                                   |
| `saltiness_preference`   | int (0–5)         |                                                   |
| `oiliness_preference`    | int (0–5)         |                                                   |
| `preferred_textures`     | string[]          | e.g. `crispy`, `tender`, `creamy`, `gelatinous`  |
| `budget_min`/`budget_max`| float             | Per-meal range, local currency (PKR for now)     |
| `dietary_requirements`   | string[]          | e.g. `halal`, `vegetarian`                       |
| `allergies`              | string[]          |                                                   |
| `disliked_ingredients`   | string[]          |                                                   |
| `taste_vector`           | float[384]        | Unit length. Dim configurable via `VECTOR_DIM`, matches Ganva's dish vectors. |
| `last_updated`           | ISO-8601 datetime | Bumps on onboarding and every interaction        |

### `Interaction` (event log)
```json
{
  "user_id": "3f9a1e2b-...-uuid",
  "dish_id": "90443b39-...-uuid",
  "action": "order",
  "ts": "2026-08-26T10:16:03.201+00:00"
}
```

`action` is one of: `"click" | "save" | "order"`. Weighting is currently the
same for all three — call this out in the ranking engine if you want different
strengths.

### `SimilarUser`
```json
{ "user_id": "9f8e7d6c-...-uuid", "score": 0.812 }
```
`score` is cosine similarity in `[-1, 1]` — higher is more similar.

### `ContextSignal`
```json
{
  "user_id": "3f9a1e2b-...-uuid",
  "current_period": "dinner",
  "preferred_period": "dinner",
  "period_weights": { "lunch": 0.2, "dinner": 0.8 },
  "context_match": true
}
```
`current_period`/`preferred_period` are one of `breakfast | lunch | dinner | late_night`
(hour ranges: 5–11, 11–16, 16–22, 22–5). `preferred_period` and `context_match`
are `null` until the user has at least one logged interaction.

### `PopularityEntry`
```json
{ "dish_id": "90443b39-...-uuid", "score": 0.72 }
```
`score` is in `[0, 1]`, normalized against the current highest-scoring dish.
Underlying weights: `order=3, save=2, click=1`, summed per dish across all
users. Recomputed on every request — there's no caching yet, fine at sprint
scale.

---

## Endpoints

### `GET /api/user/{user_id}/taste-vector`
Return the user's full `UserTaste`. `404` if unknown.

### `GET /api/user/{user_id}/interaction`
Return `Interaction[]` for this user, oldest first.

### `POST /api/user/{user_id}/interaction`
Log an interaction and nudge the user's taste vector toward the dish (EMA
with α from `EMA_ALPHA`, default 0.15).

**Request body:**
```json
{ "dish_id": "90443b39-...-uuid", "action": "click" }
```

**Response:**
```json
{
  "ok": true,
  "user_id": "3f9a1e2b-...-uuid",
  "dish_id": "90443b39-...-uuid",
  "action": "click",
  "vector_updated": true
}
```

`vector_updated` is `false` when the dish is unknown to the personalization
side (interaction is still logged; the vector just isn't nudged).

### `GET /api/user/{user_id}/similar?k=5`
Cosine-similar users. Excludes the caller.

### `GET /api/user/{user_id}/context`
Context-aware signal (the 3rd personalization mode alongside content-based
and collaborative): which meal period this user tends to interact in, vs.
the current period right now. `404` if unknown user.

### `GET /api/popularity`
All dishes with at least one interaction, `PopularityEntry[]`, sorted
descending by score. Source for the ranking engine's popularity weight.

### `GET /api/popularity/{dish_id}`
Single dish's popularity score. `0.0` if the dish has no interactions yet
(not a 404 — an unseen dish is a valid, just-unpopular state).

---

## Onboarding (UI + form POST)

- `GET  /onboarding` — HTML form
- `POST /onboarding` — form-encoded body, redirects (303) to `/onboarding/done?user_id=…`

Programmatic clients should hit `POST /api/user/{id}/interaction` after
onboarding rather than driving the form.

### Onboarding form fields
| Field                  | Type                      |
|-------------------------|---------------------------|
| `cuisines`               | string[]                  |
| `favourite_dishes`       | string (comma-separated)  |
| `dietary`                 | string[]                  |
| `textures`                | string[]                  |
| `allergies`               | string (comma-separated)  |
| `disliked_ingredients`    | string (comma-separated)  |
| `spice_preference`        | int (0–5)                 |
| `sweetness_preference`    | int (0–5)                 |
| `sourness_preference`     | int (0–5)                 |
| `saltiness_preference`    | int (0–5)                 |
| `oiliness_preference`     | int (0–5)                 |
| `budget_min`/`budget_max` | float                     |

---

## Notes for Esha

- Filter by `budget_min`/`budget_max`, `dietary_requirements`, `allergies`,
  and distance **before** you score with the taste vector — the vector is
  a soft signal, not a hard constraint.
- Use `cosine_similarity(user.taste_vector, dish.vector)` as the `taste`
  component of the weighted score (45% weight per the sprint spec). Both
  vectors are 384-dim, matching Ganva's `EMBEDDING_DIMENSION`.
- After every user action in the feed, POST it back to
  `/api/user/{user_id}/interaction`. Fire-and-forget is fine; the endpoint
  is idempotent per-event (each POST creates one log row).
- Popularity weight (5%): pull from `GET /api/popularity` instead of
  computing your own — it's sourced from the same interaction log this
  module owns, weighted `order=3, save=2, click=1`, normalized to [0,1].
- Context-aware signal isn't in the weighted-score spec, but it's available
  at `GET /api/user/{id}/context` if you want it as a tiebreaker or a small
  boost for dishes tagged to the user's `preferred_period`.

## Notes for Ganva

- `user_id` and `dish_id` are UUID strings on this side too, matching your
  contracts. Mock dishes (`scripts/generate_mock_dishes.py`) now generate
  deterministic `uuid5` ids and 384-dim vectors so local dev matches your
  real catalog's shape.
- Interim: personalization reads `data/mock_dishes.json`. Once your
  `/dishes` API or seed file is ready, swap `app/dish_store.py` to read
  from there instead — only that one module needs to change.
- Supabase table shapes assumed by `SupabaseRepository` (adjust to match
  your actual migrations if they differ):
  ```sql
  create table users (
    user_id uuid primary key,
    preferred_cuisines jsonb not null default '[]',
    favourite_dishes jsonb not null default '[]',
    spice_preference int not null,
    sweetness_preference int not null,
    sourness_preference int not null,
    saltiness_preference int not null,
    oiliness_preference int not null,
    preferred_textures jsonb not null default '[]',
    budget_min numeric not null,
    budget_max numeric not null,
    dietary_requirements jsonb not null default '[]',
    allergies jsonb not null default '[]',
    disliked_ingredients jsonb not null default '[]',
    taste_vector jsonb not null,
    last_updated timestamptz not null default now()
  );
  create table interactions (
    id bigserial primary key,
    user_id uuid not null references users(user_id),
    dish_id uuid not null,
    action text not null check (action in ('click','save','order')),
    ts timestamptz not null default now()
  );
  ```
