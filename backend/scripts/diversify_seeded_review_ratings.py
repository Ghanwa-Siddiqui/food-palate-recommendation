"""Diversify seeded review ratings so unrelated dishes stop converging on
identical average rating/sentiment, in development data.

Both customer-taste-demo seed batches assign ratings via an index/slot-based
formula that has nothing to do with which dish is being reviewed (see
seed_customer_taste_demo.py's plan(): `if slot < 2 or global_index % 20 ==
10: rating = 5 if ... else 4 ...`). Since many different reviewers across
many different dishes land on the same slot/index pattern, dozens of
unrelated dishes end up with the exact same average rating - and therefore
the exact same computed review_sentiment (observed live: ~10 dishes all at
review_sentiment 0.826 or 0.844, nothing in between).

This is a one-off development-data correction, not a schema change or a
rewrite of either seed script: it re-derives each seeded review's rating
from a hash of (dish_id, review_id) instead of (user_index, slot), so the
*dish* - not the reviewer's position in a list - determines the outcome.
Ratings stay within their original positive/negative/neutral tier (a
review that was positive stays positive, 4 or 5, never drops to a "bad"
score), so this only adds variety within each tier; it doesn't invent
opinions the seed data never expressed. After changing ratings, review
sentiment/spice/oiliness/tags/embedding are recomputed via the same
SeedReviewProcessor pipeline the seed scripts already use (not hand-set),
and dish aggregates are recomputed via the same _recompute() the app's own
review endpoint uses - so this produces exactly the same fields a real
review submission would, just with more realistic dish-to-dish variety.

Naturally idempotent: the target rating is a pure function of
(dish_id, review_id, tier), where tier is derived from the review's
*current* rating - since every value in a tier's pool still falls in that
same tier's classification range, re-running recomputes the identical
target and changes nothing further.
"""

from __future__ import annotations

import argparse
import hashlib
import secrets
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.routes.reviews import _process, _recompute
from app.core.config import get_settings
from app.db.session import get_engine
from app.models.dish import Dish
from app.models.review import Review
from scripts.seed import SeedSafetyError, extract_supabase_project_ref, verify_seed_preconditions
from scripts.seed_customer_taste_demo import BATCH as WAVE1_BATCH
from scripts.seed_customer_taste_demo import SeedReviewProcessor
from scripts.seed_customer_taste_demo_wave2 import BATCH as WAVE2_BATCH

CORRECTION_CONFIRMATION = "DIVERSIFY_CHASKA_SEEDED_REVIEW_RATINGS"

SEED_BATCH_PREFIXES = (f"{WAVE1_BATCH}:review:", f"{WAVE2_BATCH}:review:")

# Ratings a review may land on within its own tier - weighted so most stay
# near their original value, with real spread instead of only two outcomes.
_POSITIVE_POOL = (5, 5, 5, 4, 4, 4, 4, 3)
_NEGATIVE_POOL = (1, 1, 2, 2, 2, 3)


def _tier(rating: int) -> str:
    if rating >= 4:
        return "positive"
    if rating <= 2:
        return "negative"
    return "neutral"


def _target_rating(dish_id: UUID, review_id: UUID, tier: str) -> int:
    if tier == "neutral":
        return 3
    pool = _POSITIVE_POOL if tier == "positive" else _NEGATIVE_POOL
    digest = hashlib.sha256(f"{dish_id}:{review_id}".encode()).hexdigest()
    return pool[int(digest, 16) % len(pool)]


def _seed_review_filter():
    return or_(*(Review.submission_key.like(f"{prefix}%") for prefix in SEED_BATCH_PREFIXES))


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


@dataclass(frozen=True)
class DiversifyResult:
    status: str
    reviews_changed: int
    dishes_recomputed: int


def diversify_seeded_review_ratings(session: Session) -> DiversifyResult:
    reviews = list(session.scalars(select(Review).where(_seed_review_filter())))
    if not reviews:
        raise SeedSafetyError("no seeded reviews found to diversify")

    changed = [
        review
        for review in reviews
        if _target_rating(review.dish_id, review.id, _tier(review.rating)) != review.rating
    ]
    if not changed:
        return DiversifyResult("already_corrected", 0, 0)

    for review in changed:
        review.rating = _target_rating(review.dish_id, review.id, _tier(review.rating))

    processor = SeedReviewProcessor()
    for review in changed:
        _process(review, processor)
    session.flush()

    touched_dish_ids = {review.dish_id for review in changed}
    dishes = {
        dish.id: dish
        for dish in session.scalars(select(Dish).where(Dish.id.in_(touched_dish_ids)))
    }
    reviews_by_dish: dict[UUID, list[Review]] = {}
    for review in session.scalars(
        select(Review).where(Review.dish_id.in_(touched_dish_ids), Review.archived_at.is_(None))
    ):
        reviews_by_dish.setdefault(review.dish_id, []).append(review)
    for dish_id, dish in dishes.items():
        _recompute(dish, reviews_by_dish.get(dish_id, []))
    session.flush()

    return DiversifyResult("corrected", len(changed), len(dishes))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirmation", required=True)
    args = parser.parse_args()
    settings = get_settings()
    try:
        authorize_correction(
            database_url=settings.database_url,
            app_env=settings.app_env,
            confirmation=args.confirmation,
            expected_project_ref=settings.expected_supabase_project_ref,
        )
        with Session(get_engine()) as session, session.begin():
            verify_seed_preconditions(session, require_empty_catalog=False)
            result = diversify_seeded_review_ratings(session)
    except SeedSafetyError as error:
        raise SystemExit(str(error)) from error

    if result.status == "already_corrected":
        print("Seeded review ratings are already diversified; no changes made")
    else:
        print(
            f"Diversified {result.reviews_changed} reviews across "
            f"{result.dishes_recomputed} dishes"
        )


if __name__ == "__main__":
    main()
