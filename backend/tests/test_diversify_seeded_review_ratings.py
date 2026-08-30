import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.reviews import _process, _recompute
from app.models.dish import Dish
from app.models.review import Review
from app.models.user import User
from scripts.diversify_seeded_review_ratings import (
    CORRECTION_CONFIRMATION,
    _tier,
    authorize_correction,
    diversify_seeded_review_ratings,
)
from scripts.seed import SeedSafetyError
from scripts.seed_customer_taste_demo import BATCH as WAVE1_BATCH
from scripts.seed_customer_taste_demo import SeedReviewProcessor
from scripts.seed_customer_taste_demo_wave2 import BATCH as WAVE2_BATCH
from tests.factories import dish as make_dish
from tests.factories import restaurant as make_restaurant

REMOTE_URL = "postgresql://postgres.projectref:secret@pooler.supabase.com:6543/postgres"


def _user(email: str) -> User:
    return User(id=uuid.uuid4(), name=email.split("@")[0], email=email, role="customer")


def _seeded_review(*, dish_id, user_id, rating: int, batch: str, slug: str, text: str) -> Review:
    return Review(
        id=uuid.uuid4(),
        dish_id=dish_id,
        user_id=user_id,
        rating=rating,
        text=text,
        submission_key=f"{batch}:review:{slug}",
    )


def _seed_dishes_and_reviews(session: Session, *, count: int, rating: int, batch: str, salt: str = ""):
    """Build reviews the way the real seed scripts leave them: already
    processed (processing_status="complete", real sentiment/embedding) and
    already rolled up onto their dish - not the "just inserted" state a raw
    Review() row would have."""
    place = make_restaurant()
    session.add(place)
    session.flush()

    processor = SeedReviewProcessor()
    dishes = []
    reviews = []
    for index in range(count):
        item = make_dish(place.id, name=f"Dish {salt}{index}")
        session.add(item)
        session.flush()
        reviewer = _user(f"reviewer{salt}{index}@chaska.dev")
        session.add(reviewer)
        session.flush()
        review = _seeded_review(
            dish_id=item.id,
            user_id=reviewer.id,
            rating=rating,
            batch=batch,
            slug=f"{salt}{index:03d}",
            text="Loved the flavour and texture." if rating >= 4 else "Too bland for my taste.",
        )
        _process(review, processor)
        session.add(review)
        session.flush()
        _recompute(item, [review])
        dishes.append(item)
        reviews.append(review)
    session.flush()
    session.commit()
    return dishes, reviews


def test_diversify_spreads_ratings_within_the_same_tier_and_recomputes_dish_aggregates(
    session: Session,
):
    dishes, reviews = _seed_dishes_and_reviews(
        session, count=12, rating=5, batch=WAVE1_BATCH
    )

    with Session(session.get_bind()) as correction_session, correction_session.begin():
        result = diversify_seeded_review_ratings(correction_session)

    assert result.status == "corrected"
    assert result.reviews_changed > 0
    assert result.dishes_recomputed > 0

    session.expire_all()
    updated = session.scalars(
        select(Review).where(Review.id.in_([r.id for r in reviews]))
    ).all()
    ratings = {r.rating for r in updated}
    assert ratings <= {3, 4, 5}
    assert len(ratings) > 1, "ratings should spread out, not stay uniformly 5"
    assert all(r.rating >= 3 for r in updated), "positive reviews must never drop below neutral"
    assert all(r.processing_status == "complete" for r in updated)
    assert all(r.sentiment is not None for r in updated)

    for item in session.scalars(select(Dish).where(Dish.id.in_([d.id for d in dishes]))):
        assert item.review_count == 1
        assert item.review_average == pytest.approx(next(
            r.rating for r in updated if r.dish_id == item.id
        ))
        assert item.review_sentiment is not None


def test_diversify_preserves_negative_and_neutral_tiers(session: Session):
    negative_dishes, negative_reviews = _seed_dishes_and_reviews(
        session, count=8, rating=1, batch=WAVE1_BATCH
    )

    with Session(session.get_bind()) as correction_session, correction_session.begin():
        diversify_seeded_review_ratings(correction_session)

    session.expire_all()
    updated = session.scalars(
        select(Review).where(Review.id.in_([r.id for r in negative_reviews]))
    ).all()
    assert all(r.rating <= 3 for r in updated), "negative reviews must never turn positive"
    assert {_tier(r.rating) for r in updated} <= {"negative", "neutral"}


def test_diversify_only_touches_seeded_batches(session: Session):
    place = make_restaurant()
    session.add(place)
    session.flush()
    item = make_dish(place.id)
    session.add(item)
    session.flush()
    reviewer = _user("real.diner@chaska.dev")
    session.add(reviewer)
    session.flush()
    organic = Review(
        id=uuid.uuid4(),
        dish_id=item.id,
        user_id=reviewer.id,
        rating=5,
        text="Genuinely great, ordered again the next day.",
        submission_key="organic-review-0001",
    )
    session.add(organic)
    session.commit()

    with Session(session.get_bind()) as correction_session:
        with pytest.raises(SeedSafetyError, match="no seeded reviews"):
            with correction_session.begin():
                diversify_seeded_review_ratings(correction_session)

    session.expire_all()
    untouched = session.get(Review, organic.id)
    assert untouched.rating == 5
    assert untouched.processing_status == "pending"


def test_diversify_covers_both_wave1_and_wave2_batches(session: Session):
    _, wave1_reviews = _seed_dishes_and_reviews(
        session, count=3, rating=5, batch=WAVE1_BATCH, salt="w1-"
    )
    _, wave2_reviews = _seed_dishes_and_reviews(
        session, count=3, rating=5, batch=WAVE2_BATCH, salt="w2-"
    )

    with Session(session.get_bind()) as correction_session, correction_session.begin():
        result = diversify_seeded_review_ratings(correction_session)

    assert result.reviews_changed <= len(wave1_reviews) + len(wave2_reviews)
    session.expire_all()
    all_ids = [r.id for r in wave1_reviews + wave2_reviews]
    updated = session.scalars(select(Review).where(Review.id.in_(all_ids))).all()
    assert all(r.processing_status == "complete" for r in updated)


def test_diversify_is_idempotent(session: Session):
    _seed_dishes_and_reviews(session, count=10, rating=4, batch=WAVE1_BATCH)

    with Session(session.get_bind()) as correction_session, correction_session.begin():
        first = diversify_seeded_review_ratings(correction_session)
    assert first.status == "corrected"

    with Session(session.get_bind()) as correction_session, correction_session.begin():
        second = diversify_seeded_review_ratings(correction_session)
    assert (second.status, second.reviews_changed) == ("already_corrected", 0)


def _authorization_values():
    return {
        "database_url": REMOTE_URL,
        "app_env": "development",
        "confirmation": CORRECTION_CONFIRMATION,
        "expected_project_ref": "projectref",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("app_env", "production"),
        ("confirmation", None),
        ("confirmation", "wrong"),
        ("expected_project_ref", None),
        ("expected_project_ref", "differentref"),
    ],
)
def test_diversify_requires_every_authorization_gate(field: str, value: str | None):
    values = _authorization_values()
    values[field] = value
    with pytest.raises(SeedSafetyError):
        authorize_correction(**values)


def test_diversify_accepts_exact_development_authorization():
    authorize_correction(**_authorization_values())
