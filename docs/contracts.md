# Personalization Engine — API Contracts

Owner: Manahil · Module: `feature/personalization-manahil`

This is the surface the **Ranking Engine (Esha)** and **Feed UI (Esha)** call.
Interaction events also flow back in here from the feed. Backwards-compatible
changes only after Day 2.

Base URL: `/api`

---

## Data shapes

### `UserTaste`
The full user profile stored server-side and returned by the taste-vector endpoint.

```json
{
  "user_id": "u_a1b2c3d4e5",
  "taste_vector": [0.031, -0.114, 0.087, "…128 floats total"],
  "budget": 1500,
  "dietary": ["halal"],
  "spice_pref": 3,
  "last_updated": "2026-08-25T10:14:22.913+00:00"
}
```

| Field           | Type              | Notes                                            |
|-----------------|-------------------|--------------------------------------------------|
| `user_id`       | string            | `u_` prefix + 10 hex chars                       |
| `taste_vector`  | float[128]        | Unit length. Dim configurable via `VECTOR_DIM`.  |
| `budget`        | int               | Per-meal ceiling, local currency (PKR for now)   |
| `dietary`       | string[]          | e.g. `halal`, `vegetarian`, `no-beef`            |
| `spice_pref`    | int (0–4)         | 0 = none, 4 = very hot                           |
| `last_updated`  | ISO-8601 datetime | Bumps on onboarding and every interaction        |

### `Interaction` (event log)
```json
{
  "user_id": "u_a1b2c3d4e5",
  "dish_id": "d_003",
  "action": "order",
  "ts": "2026-08-25T10:16:03.201+00:00"
}
```

`action` is one of: `"click" | "save" | "order"`. Weighting is currently the
same for all three — call this out in the ranking engine if you want different
strengths.

### `SimilarUser`
```json
{ "user_id": "u_9f8e7d6c5b", "score": 0.812 }
```
`score` is cosine similarity in `[-1, 1]` — higher is more similar.

### `ContextSignal`
```json
{
  "user_id": "u_a1b2c3d4e5",
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
{ "dish_id": "d_003", "score": 0.72 }
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
{ "dish_id": "d_003", "action": "click" }
```

**Response:**
```json
{
  "ok": true,
  "user_id": "u_a1b2c3d4e5",
  "dish_id": "d_003",
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
| Field            | Type       |
|------------------|------------|
| `cuisines`       | string[]   |
| `favorite_foods` | string (comma-separated) |
| `dietary`        | string[]   |
| `spice_pref`     | int (0–4)  |
| `budget`         | int        |

---

## Notes for Esha

- Filter by `budget`, `dietary`, and distance **before** you score with the
  taste vector — the vector is a soft signal, not a hard constraint.
- Use `cosine_similarity(user.taste_vector, dish.vector)` as the `taste`
  component of the weighted score (45% weight per the sprint spec).
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

- Dish records must include `vector: float[128]` matching `VECTOR_DIM`.
- Interim: personalization reads `data/mock_dishes.json`. On Day 2, swap
  `app/dish_store.py` to hit your `/dishes` API or read your seed file.
- Supabase table shapes assumed by `SupabaseRepository`:
  ```sql
  create table users (
    user_id text primary key,
    taste_vector jsonb not null,
    budget int not null,
    dietary jsonb not null,
    spice_pref int not null,
    last_updated timestamptz not null default now()
  );
  create table interactions (
    id bigserial primary key,
    user_id text not null references users(user_id),
    dish_id text not null,
    action text not null check (action in ('click','save','order')),
    ts timestamptz not null default now()
  );
  ```
