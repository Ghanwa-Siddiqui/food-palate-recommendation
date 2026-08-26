import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.interaction import InteractionRead
from app.schemas.review import ReviewRead
from app.schemas.user import UserRead


def test_user_review_and_interaction_schemas_validate_owned_entities():
    now = datetime.now(UTC)
    user_id = uuid.uuid4()
    dish_id = uuid.uuid4()

    user = UserRead(
        id=user_id,
        name="Test User",
        email="test@example.test",
        created_at=now,
        updated_at=now,
    )
    review = ReviewRead(
        id=uuid.uuid4(),
        user_id=user_id,
        dish_id=dish_id,
        rating=5,
        text="Great",
        created_at=now,
    )
    interaction = InteractionRead(
        id=uuid.uuid4(),
        user_id=user_id,
        dish_id=dish_id,
        action="click",
        ts=now,
    )

    assert user.id == review.user_id == interaction.user_id
    assert interaction.ts == now


def test_review_and_interaction_schemas_reject_invalid_values():
    now = datetime.now(UTC)
    values = {"id": uuid.uuid4(), "user_id": uuid.uuid4(), "dish_id": uuid.uuid4()}

    with pytest.raises(ValidationError):
        ReviewRead(**values, rating=0, text=None, created_at=now)
    with pytest.raises(ValidationError):
        InteractionRead(**values, action="view", ts=now)
