import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from app.models.interaction import Interaction
from app.models.review import Review
from app.models.user import User
from app.schemas.ranking import FeedResponse
from app.services.ranking.scoring import WEIGHTS
from tests.factories import dish, restaurant

VECTOR = [1.0] + [0.0] * 383


def user(name, *, public=False, vector=VECTOR):
    return User(
        id=uuid.uuid4(),
        name=name,
        email=f"{uuid.uuid4()}@example.test",
        role="customer",
        onboarding_complete=True,
        taste_vector=vector,
        show_review_display_name=public,
    )


def interaction(who, menu_item, action, suffix):
    return Interaction(
        user_id=who.id,
        dish_id=menu_item.id,
        action=action,
        client_event_id=f"event-{suffix}-{uuid.uuid4()}",
        ts=datetime.now(UTC),
    )


def review(
    who, menu_item, rating=5, sentiment=0.9, text="Excellent rich biryani with balanced spice."
):
    return Review(
        user_id=who.id,
        dish_id=menu_item.id,
        rating=rating,
        sentiment=sentiment,
        text=text,
        submission_key=f"review-{uuid.uuid4()}",
        processing_status="complete",
        updated_at=datetime.now(UTC),
    )


def setup_twins(session, *, public=True, neighbours=1):
    current = user("Current")
    twins = [
        user("Maham" if index == 0 else f"Diner {index}", public=public)
        for index in range(neighbours)
    ]
    place = restaurant(name="Twin Kitchen", available=True)
    session.add_all([current, *twins, place])
    session.flush()
    shared = dish(place.id, name="Chicken Biryani", price=Decimal("600"))
    discovery = dish(place.id, name="Mutton Pulao", price=Decimal("700"))
    session.add_all([shared, discovery])
    session.flush()
    rows = [interaction(current, shared, "like", "current-like")]
    for index, twin in enumerate(twins):
        rows.extend(
            [
                interaction(twin, shared, "like", f"twin-like-{index}"),
                interaction(twin, discovery, "save", f"twin-save-{index}"),
                review(twin, discovery),
            ]
        )
    session.add_all(rows)
    session.commit()
    return current, twins, shared, discovery


def test_similar_users_promote_positive_review_with_safe_named_evidence(client, session):
    current, _, _, discovery = setup_twins(session)
    response = client.get(f"/ranking/feed/{current.id}")
    assert response.status_code == 200
    payload = FeedResponse.model_validate(response.json())
    item = next(item for item in payload.items if item.dish_id == discovery.id)
    assert payload.collaborative_available and payload.similar_user_count == 1
    assert item.collaborative_score and item.collaborative_score > 50
    assert item.collaborative_reviewer_name == "Maham"
    assert "Excellent rich biryani" in item.collaborative_review_excerpt
    serialized = response.text
    assert (
        "@example.test" not in serialized and str(current.id) not in item.collaborative_explanation
    )


def test_opted_out_reviewer_is_anonymous_and_multiple_neighbours_aggregate(client, session):
    current, _, _, discovery = setup_twins(session, public=False, neighbours=3)
    payload = client.get(f"/ranking/feed/{current.id}").json()
    item = next(item for item in payload["items"] if item["dish_id"] == str(discovery.id))
    assert payload["similar_user_count"] == 3
    assert item["collaborative_reviewer_name"] == "Anonymous Chaska diner"
    assert "3 diners" in item["collaborative_explanation"]


def test_one_shared_click_is_insufficient_and_cold_start_stays_content_based(client, session):
    current, twin = user("Current"), user("Twin", public=True)
    place = restaurant(available=True)
    session.add_all([current, twin, place])
    session.flush()
    shared, discovery = dish(place.id, name="Click Dish"), dish(place.id, name="Discovery Dish")
    session.add_all([shared, discovery])
    session.flush()
    session.add_all(
        [
            interaction(current, shared, "click", "one"),
            interaction(twin, shared, "click", "two"),
            interaction(twin, discovery, "like", "three"),
        ]
    )
    session.commit()
    payload = client.get(f"/ranking/feed/{current.id}").json()
    assert payload["collaborative_available"] is False and payload["similar_user_count"] == 0
    assert all(item["collaborative_explanation"] is None for item in payload["items"])
    assert len(payload["items"]) == 2


def test_negative_or_disliked_dishes_never_receive_collaborative_boost(client, session):
    current, twins, _, discovery = setup_twins(session)
    negative = session.scalar(
        select(Review).where(Review.user_id == twins[0].id, Review.dish_id == discovery.id)
    )
    negative.rating, negative.sentiment = 1, 0.1
    session.commit()
    item = next(
        item
        for item in client.get(f"/ranking/feed/{current.id}").json()["items"]
        if item["dish_id"] == str(discovery.id)
    )
    assert item["collaborative_score"] is None
    session.add(interaction(current, discovery, "dislike", "current-dislike"))
    session.commit()
    payload = client.get(f"/ranking/feed/{current.id}").json()
    assert str(discovery.id) not in {item["dish_id"] for item in payload["items"]}
    assert twins[0].id != current.id


def test_hard_filters_inactive_and_stable_order_and_weights(client, session):
    current, _, _, discovery = setup_twins(session)
    discovery.allergens = ["nuts"]
    current.allergies = ["nuts"]
    inactive = dish(discovery.restaurant_id, name="Inactive Twin Dish", availability=False)
    session.add(inactive)
    session.commit()
    first = client.get(f"/ranking/feed/{current.id}", params={"allergies": "nuts"}).json()
    second = client.get(f"/ranking/feed/{current.id}", params={"allergies": "nuts"}).json()
    assert [item["dish_id"] for item in first["items"]] == [
        item["dish_id"] for item in second["items"]
    ]
    ids = {item["dish_id"] for item in first["items"]}
    assert str(discovery.id) not in ids and str(inactive.id) not in ids
    assert WEIGHTS == {
        "taste": 0.45,
        "food_profile": 0.20,
        "review": 0.10,
        "distance": 0.10,
        "price": 0.10,
        "popularity": 0.05,
    }
