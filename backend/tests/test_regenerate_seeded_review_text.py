import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dish import Dish
from app.models.review import Review
from app.models.user import User
from app.services.data_core.review_processing import ProcessedReview
from scripts.regenerate_seeded_review_text import (
    CORRECTION_CONFIRMATION,
    authorize_correction,
    regenerate_seeded_review_text,
)
from scripts.seed import SeedSafetyError
from scripts.seed_customer_taste_demo import BATCH as WAVE1_BATCH
from scripts.seed_customer_taste_demo_wave2 import BATCH as WAVE2_BATCH
from tests.factories import dish as make_dish
from tests.factories import restaurant as make_restaurant

REMOTE_URL = "postgresql://postgres.projectref:secret@pooler.supabase.com:6543/postgres"


class _FakeWriter:
    def __init__(self):
        self.calls = []

    def write(self, *, dish_name: str, cuisine: str, rating: int) -> str:
        self.calls.append((dish_name, cuisine, rating))
        return f"Generated review #{len(self.calls)} for {dish_name} ({rating} stars)."


class _FakeProcessor:
    def process(self, text: str, rating: int) -> ProcessedReview:
        return ProcessedReview(
            sentiment={1: 0.1, 2: 0.3, 3: 0.5, 4: 0.75, 5: 0.9}[rating],
            spice=0.5,
            oiliness=0.5,
            tags=["fresh"],
            embedding=[0.42] * 384,
        )


def _user(email: str) -> User:
    return User(id=uuid.uuid4(), name=email.split("@")[0], email=email, role="customer")


def _seed_dish_and_reviews(session: Session, *, count: int, batch: str):
    place = make_restaurant()
    session.add(place)
    session.flush()
    item = make_dish(place.id, name="Chicken Karahi")
    session.add(item)
    session.flush()

    reviews = []
    for index in range(count):
        reviewer = _user(f"reviewer{index}@chaska.dev")
        session.add(reviewer)
        session.flush()
        review = Review(
            id=uuid.uuid4(),
            dish_id=item.id,
            user_id=reviewer.id,
            rating=4,
            text=f"I tried the {item.name}. It was fresh, flavorful and worth ordering again.",
            submission_key=f"{batch}:review:{index:03d}",
        )
        session.add(review)
        reviews.append(review)
    session.commit()
    return item, reviews


def test_regenerate_replaces_text_and_reprocesses_every_seeded_review(session: Session):
    item, reviews = _seed_dish_and_reviews(session, count=5, batch=WAVE1_BATCH)
    writer = _FakeWriter()

    with Session(session.get_bind()) as correction_session:
        count = regenerate_seeded_review_text(
            correction_session, writer=writer, processor=_FakeProcessor()
        )

    assert count == 5
    assert len(writer.calls) == 5
    assert all(call[0] == "Chicken Karahi" and call[2] == 4 for call in writer.calls)

    session.expire_all()
    updated = session.scalars(select(Review).where(Review.id.in_([r.id for r in reviews]))).all()
    assert all("Generated review" in r.text for r in updated)
    assert all(r.processing_status == "complete" for r in updated)
    assert all(r.sentiment == pytest.approx(0.75) for r in updated)
    assert all(len(r.review_embedding) == 384 for r in updated)

    refreshed_dish = session.get(Dish, item.id)
    assert refreshed_dish.review_count == 5
    assert refreshed_dish.review_sentiment == pytest.approx(0.75)


def test_regenerate_commits_in_batches_for_a_larger_run(session: Session):
    _seed_dish_and_reviews(session, count=23, batch=WAVE1_BATCH)

    with Session(session.get_bind()) as correction_session:
        count = regenerate_seeded_review_text(
            correction_session, writer=_FakeWriter(), processor=_FakeProcessor()
        )

    assert count == 23


def test_regenerate_only_touches_seeded_batches(session: Session):
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
            regenerate_seeded_review_text(
                correction_session, writer=_FakeWriter(), processor=_FakeProcessor()
            )

    session.expire_all()
    untouched = session.get(Review, organic.id)
    assert untouched.text == "Genuinely great, ordered again the next day."
    assert untouched.processing_status == "pending"


def test_regenerate_covers_both_wave1_and_wave2_batches(session: Session):
    place = make_restaurant()
    session.add(place)
    session.flush()
    item = make_dish(place.id)
    session.add(item)
    session.flush()
    reviews = []
    for batch, slug in ((WAVE1_BATCH, "w1"), (WAVE2_BATCH, "w2")):
        reviewer = _user(f"{slug}@chaska.dev")
        session.add(reviewer)
        session.flush()
        review = Review(
            id=uuid.uuid4(),
            dish_id=item.id,
            user_id=reviewer.id,
            rating=3,
            text="templated text",
            submission_key=f"{batch}:review:{slug}",
        )
        session.add(review)
        reviews.append(review)
    session.commit()

    with Session(session.get_bind()) as correction_session:
        count = regenerate_seeded_review_text(
            correction_session, writer=_FakeWriter(), processor=_FakeProcessor()
        )

    assert count == 2
    session.expire_all()
    updated = session.scalars(select(Review).where(Review.id.in_([r.id for r in reviews]))).all()
    assert all(r.processing_status == "complete" for r in updated)


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
def test_regenerate_requires_every_authorization_gate(field: str, value: str | None):
    values = _authorization_values()
    values[field] = value
    with pytest.raises(SeedSafetyError):
        authorize_correction(**values)


def test_regenerate_accepts_exact_development_authorization():
    authorize_correction(**_authorization_values())
