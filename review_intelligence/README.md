# Namak Review Intelligence

This independent module turns food-review text into structured scores and tags, then combines reviews into a dish-level summary for other Namak modules. It does not rank restaurants, store restaurant records, manage users, or provide UI/authentication.

## Layout

`data/reviews.csv` is a 50-review sample input corpus (10 dishes, 5 reviews each). `src/extractor.py` calls local Ollama; `src/embeddings.py` supplies optional local vectors; `src/aggregator.py` makes deterministic summaries; `api/review_api.py` exposes those summaries. `scripts/process_reviews.py` produces `data/review_features.csv`.

## Installation and Ollama

Use Python 3.10+ from the repository root:

```bash
pip install -r review_intelligence/requirements.txt
ollama pull llama3.2
ollama serve
```

Ollama is a local system dependency. Select another installed model without changing code:

```powershell
$env:OLLAMA_MODEL = "llama3.2"
$env:OLLAMA_HOST = "http://localhost:11434"  # optional
```

The extractor asks Ollama to return only JSON, validates all scores in `[0, 1]`, and reports malformed JSON or unavailable Ollama explicitly. Missing spice/oiliness defaults to `0.5`, and unclear sentiment defaults to `0.5`, as instructed to the model. A failed review is logged and skipped during batch processing rather than stopping the whole job.

## Process reviews and embeddings

```bash
python review_intelligence/scripts/process_reviews.py
python review_intelligence/scripts/process_reviews.py --with-embeddings
```

The second command uses the free `all-MiniLM-L6-v2` Sentence Transformers model (override with `REVIEW_EMBEDDING_MODEL`). It may download the model on first use. `flavor_tags` and each per-review `embedding` are saved as JSON arrays in CSV. The aggregator mean-pools equal-length review vectors into `review_vector`; without embeddings it safely returns `[]`.

## API

First generate `data/review_features.csv`, then run:

```bash
uvicorn review_intelligence.api.review_api:app --reload
```

`GET /reviews/{dish_id}/summary` returns the shared integration contract:

```json
{
  "dish_id": "D001",
  "avg_sentiment": 0.88,
  "spice_level": 0.82,
  "oiliness": 0.61,
  "flavor_tags": ["spicy", "rich gravy", "tender"],
  "review_vector": []
}
```

Unknown IDs return `404` with `{ "detail": "No review summary found ..." }`. If the feature CSV has not yet been produced, the endpoint reports `503` with instructions to run the processor.

## Tests

```bash
pytest review_intelligence/tests -q
```

Tests use fake LLM responses and a temporary feature CSV, so neither Ollama nor the embedding model is needed. In production, the batch script is the integration path that requires Ollama.
