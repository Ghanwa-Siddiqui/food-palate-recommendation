"""Rewrite every seeded review's text with a real local LLM, in development
data, then reprocess it through the exact same pipeline a genuine review
submission uses.

Both customer-taste-demo seed batches build review text by concatenating a
canned opening ("I tried the {dish}.") with one of a small pool of fixed
ending sentences per rating tier. At the ~800-review scale this reads as
obviously templated - many reviews across different dishes are close to
word-for-word identical. It also means the seeded reviews' sentiment/
spice/oiliness/embedding were computed by the seed script's rule-based
extractor and a deterministic fake embedder, not the real pipeline.

This script fixes both at once: it asks a local Ollama model
(`review_intelligence`'s existing OLLAMA_MODEL, default llama3.2) to write
one short, natural review per seeded review, grounded in that review's own
dish name/cuisine/rating so it stays specific rather than generic - then
runs the result through `LiveReviewProcessor`, the same
Ollama-extraction-plus-Sentence-Transformers-embedding pipeline the app's
own `/reviews` endpoint uses for a real submission. So a seeded review ends
up indistinguishable from a genuine one: real text, real sentiment
extraction, real embedding.

Not idempotent by design - re-running regenerates fresh text each time
(LLM output isn't deterministic), which is fine since the point is
variety, not reproducibility. Long-running: expect roughly two Ollama
calls (write, then extract) per review.
"""

from __future__ import annotations

import argparse
import secrets
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import requests
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.routes.reviews import _process, _recompute
from app.core.config import get_settings
from app.db.session import get_engine
from app.models.dish import Dish
from app.models.review import Review
from scripts.seed import SeedSafetyError, extract_supabase_project_ref, verify_seed_preconditions
from scripts.seed_customer_taste_demo import BATCH as WAVE1_BATCH
from scripts.seed_customer_taste_demo_wave2 import BATCH as WAVE2_BATCH

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from review_intelligence.src import config as review_intelligence_config  # noqa: E402
from app.services.data_core.review_processing import LiveReviewProcessor  # noqa: E402

CORRECTION_CONFIRMATION = "REGENERATE_CHASKA_SEEDED_REVIEW_TEXT"

SEED_BATCH_PREFIXES = (f"{WAVE1_BATCH}:review:", f"{WAVE2_BATCH}:review:")

_WRITE_PROMPT = """Write ONE short, natural restaurant review as if you were a real
customer. First person, 1 to 2 sentences, plain conversational language - not a
marketing blurb. Return ONLY the review text: no quotes, no preamble, no labels.

Dish: {dish_name}
Cuisine: {cuisine}
Star rating you gave it: {rating}/5 (1 = very disappointing, 5 = excellent)
"""


class ReviewWriteError(RuntimeError):
    pass


class OllamaReviewWriter:
    def __init__(
        self,
        host: str = review_intelligence_config.OLLAMA_HOST,
        model: str = review_intelligence_config.OLLAMA_MODEL,
        timeout: float = review_intelligence_config.OLLAMA_TIMEOUT_SECONDS,
    ) -> None:
        self.host, self.model, self.timeout = host.rstrip("/"), model, timeout

    def write(self, *, dish_name: str, cuisine: str, rating: int) -> str:
        prompt = _WRITE_PROMPT.format(dish_name=dish_name, cuisine=cuisine, rating=rating)
        try:
            response = requests.post(
                f"{self.host}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise ReviewWriteError(
                f"Cannot reach Ollama at {self.host}. Start it with `ollama serve` and pull "
                f"the configured model using `ollama pull {self.model}`."
            ) from exc
        if response.status_code >= 400:
            raise ReviewWriteError(f"Ollama returned HTTP {response.status_code}: {response.text}")
        try:
            text = response.json()["response"].strip().strip('"')
        except (ValueError, KeyError, TypeError) as exc:
            raise ReviewWriteError("Ollama returned a response without generated text") from exc
        if not text:
            raise ReviewWriteError("Ollama returned empty review text")
        return text


def authorize_correction(
    *,
    database_url: str,
    app_env: str,
    confirmation: str | None,
    expected_project_ref: str | None,
) -> None:
    if app_env != "development":
        raise SeedSafetyError("development-data correction requires APP_ENV=development")
    if not secrets.compare_digest(confirmation or "", CORRECTION_CONFIRMATION):
        raise SeedSafetyError("development-data correction confirmation did not match")
    if not expected_project_ref:
        raise SeedSafetyError("EXPECTED_SUPABASE_PROJECT_REF is required")
    target_project_ref = extract_supabase_project_ref(database_url)
    if not secrets.compare_digest(target_project_ref, expected_project_ref):
        raise SeedSafetyError("Supabase project reference did not match the expected target")


def _seed_review_filter():
    return or_(*(Review.submission_key.like(f"{prefix}%") for prefix in SEED_BATCH_PREFIXES))


def regenerate_seeded_review_text(
    session: Session,
    *,
    writer: OllamaReviewWriter,
    processor: LiveReviewProcessor,
    on_progress=None,
) -> int:
    reviews = list(
        session.scalars(select(Review).where(_seed_review_filter()).order_by(Review.id))
    )
    if not reviews:
        raise SeedSafetyError("no seeded reviews found to regenerate")

    dishes = {
        dish.id: dish
        for dish in session.scalars(
            select(Dish).where(Dish.id.in_({review.dish_id for review in reviews}))
        )
    }
    touched_dish_ids: set = set()
    # Committed in small batches, not one transaction for the whole run: this
    # does roughly two Ollama calls per review, so the full job can take a
    # long time against a cloud database - a single multi-hour transaction
    # risks a connection/pool timeout that would roll back everything
    # already done. Partial progress persisting on interruption is the
    # right tradeoff for one-off dev-data cleanup like this.
    for index, review in enumerate(reviews):
        dish = dishes[review.dish_id]
        review.text = writer.write(dish_name=dish.name, cuisine=dish.cuisine, rating=review.rating)
        _process(review, processor)
        touched_dish_ids.add(dish.id)
        if (index + 1) % 10 == 0:
            session.commit()
        if on_progress:
            on_progress(index + 1, len(reviews))
    session.commit()

    reviews_by_dish = defaultdict(list)
    for review in session.scalars(
        select(Review).where(Review.dish_id.in_(touched_dish_ids), Review.archived_at.is_(None))
    ):
        reviews_by_dish[review.dish_id].append(review)
    for dish_id in touched_dish_ids:
        _recompute(dishes[dish_id], reviews_by_dish[dish_id])
    session.commit()

    return len(reviews)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirmation", required=True)
    args = parser.parse_args()
    settings = get_settings()

    def on_progress(done: int, total: int) -> None:
        if done % 10 == 0 or done == total:
            print(f"  regenerated {done}/{total}", flush=True)

    try:
        authorize_correction(
            database_url=settings.database_url,
            app_env=settings.app_env,
            confirmation=args.confirmation,
            expected_project_ref=settings.expected_supabase_project_ref,
        )
        with Session(get_engine()) as session:
            with session.begin():
                verify_seed_preconditions(session, require_empty_catalog=False)
            count = regenerate_seeded_review_text(
                session,
                writer=OllamaReviewWriter(),
                processor=LiveReviewProcessor(),
                on_progress=on_progress,
            )
    except SeedSafetyError as error:
        raise SystemExit(str(error)) from error
    except ReviewWriteError as error:
        raise SystemExit(str(error)) from error

    print(f"Regenerated text and reprocessed {count} seeded reviews")


if __name__ == "__main__":
    main()
