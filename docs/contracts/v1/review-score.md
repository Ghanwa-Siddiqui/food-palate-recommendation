# Review Intelligence → Ranking Engine: `review_score` contract

## Status

`review_score` is **not currently defined or produced** by this repository.
There is no `review_score` property in the Review Intelligence API, its Python
models, `review-summary.schema.json`, or ranking implementation. Consequently,
this document does not define a formula, weight, or derived scalar score.

The Review Intelligence module provides a dish-level review *summary*. The
Ranking Engine owner is responsible for defining any future `review_score`
calculation and for publishing it in a versioned contract before consumers rely
on it.

## Current Review Intelligence handoff

The current endpoint is:

```text
GET /reviews/{dish_id}/summary
```

It returns this backward-compatible payload shape:

```json
{
  "dish_id": "...",
  "avg_sentiment": 0.0,
  "spice_level": 0.0,
  "oiliness": 0.0,
  "flavor_tags": [],
  "review_vector": []
}
```

The fields currently available to Ranking are:

| Field | Current implementation meaning | Runtime type |
| --- | --- | --- |
| `dish_id` | Identifier used to request/associate the dish summary. | string |
| `avg_sentiment` | Arithmetic mean of extracted review sentiment. | number, normalized `0.0`–`1.0` in the Review Intelligence implementation |
| `spice_level` | Arithmetic mean of extracted spice scores. | number, normalized `0.0`–`1.0` |
| `oiliness` | Arithmetic mean of extracted oiliness scores. | number, normalized `0.0`–`1.0` |
| `flavor_tags` | Most frequent extracted tags, ordered deterministically by frequency then name. | array of strings |
| `review_vector` | Mean-pooled review embedding when per-review embeddings exist; otherwise `[]`. | array of numbers |

Per-review source data also carries a `rating` on a `1`–`5` scale, and the
backend's `Review` model enforces that range. Rating is **not** part of the
current dish-summary response and is not aggregated into a `review_score` by
the current module.

## Ranking consumption rules

Until a versioned scoring definition exists, Ranking should:

1. Treat `avg_sentiment`, `spice_level`, and `oiliness` as separate signals,
   not aliases for a scalar `review_score`.
2. Treat `flavor_tags` as descriptive metadata and `review_vector` as optional
   similarity input; an empty vector is valid and must not be interpreted as a
   zero-valued embedding.
3. Handle an unavailable summary (`404`) or unprocessed feature data (`503`)
   as missing review intelligence, using the Ranking Engine's own documented
   fallback behavior.
4. Avoid assuming that rating, review count, review recency, or confidence is
   available from this handoff; none is currently returned.

## Existing contract discrepancy requiring owner agreement

`docs/contracts/v1/review-summary.schema.json` preserves the same six-field
shape, but currently declares `avg_sentiment` as `-1`–`1`, `spice_level` and
`oiliness` as `0`–`5`, and `dish_id` as a UUID. The active Review Intelligence
implementation returns normalized `0`–`1` values and its sample corpus uses IDs
such as `D001`. This document does not change either contract.

Before an integration is finalized, the Review Intelligence and Ranking owners
must agree which source is authoritative for numeric ranges and dish-ID format,
then update the relevant versioned contract and tests together.

## Decisions still owned by Ranking

The Ranking Engine owner must define and document, with team agreement:

- whether `review_score` will exist at all;
- if it exists, its formula, range, rounding, and treatment of ratings;
- the relative weights of sentiment, ratings, tags, vectors, review count, and
  recency (if such data is added);
- confidence/minimum-review handling and missing-summary fallback behavior;
- the canonical dish-ID mapping and the authoritative numeric range contract.

No Ranking implementation should infer these decisions from this document.

## Evidence reviewed

- `review_intelligence/api/review_api.py`
- `review_intelligence/src/models.py`
- `review_intelligence/src/aggregator.py`
- `review_intelligence/README.md`
- `docs/contracts/v1/review-summary.schema.json`
- `backend/app/models/review.py`
- `backend/app/schemas/review.py`
