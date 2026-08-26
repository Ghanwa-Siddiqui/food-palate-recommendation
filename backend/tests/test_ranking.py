import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.constants import EMBEDDING_DIMENSION
from app.models.interaction import Interaction
from app.models.review import Review
from app.models.user import User
from app.schemas.ranking import FeedPreferences, FeedResponse
from app.services.ranking.generator import RankingCandidate, filter_candidates
from app.services.ranking.scoring import (
    NEUTRAL_SCORE,
    WEIGHTS,
    calculate_cosine_similarity,
    score_candidate,
)
from tests.factories import dish, restaurant


def candidate(**overrides) -> RankingCandidate:
    owner = SimpleNamespace(
        id=uuid.uuid4(),
        name="Test Restaurant",
        halal_status="claimed",
        latitude=Decimal("31.52"),
        longitude=Decimal("74.35"),
        location_verified=True,
    )
    values = {
        "id": uuid.uuid4(),
        "restaurant_id": owner.id,
        "name": "Test Dish",
        "price": Decimal("500"),
        "ingredients": ["rice"],
        "dietary_tags": ["vegetarian"],
        "allergens": [],
        "availability": True,
        "embedding": [1.0] + [0.0] * (EMBEDDING_DIMENSION - 1),
        "restaurant": owner,
    }
    values.update(overrides)
    return RankingCandidate(dish=SimpleNamespace(**values))


def test_candidate_generation_filters_budget_and_unavailable():
    rows = [candidate(), candidate(price=Decimal("1500")), candidate(availability=False)]
    result = filter_candidates(rows, FeedPreferences(budget_max=1000))
    assert result == [rows[0]]


def test_candidate_generation_filters_diet_allergy_and_disliked_ingredients():
    rows = [
        candidate(),
        candidate(dietary_tags=[]),
        candidate(allergens=["nuts"]),
        candidate(ingredients=["mushroom"]),
    ]
    preferences = FeedPreferences(
        dietary_restrictions=["vegetarian", "halal"],
        allergies=["NUTS"],
        disliked_ingredients=["Mushroom"],
    )
    assert filter_candidates(rows, preferences) == [rows[0]]


def test_halal_is_checked_on_restaurant_not_dietary_tags():
    row = candidate(dietary_tags=[])
    assert filter_candidates([row], FeedPreferences(require_halal=True)) == [row]
    row.dish.restaurant.halal_status = "unknown"
    assert filter_candidates([row], FeedPreferences(require_halal=True)) == []


def test_distance_filter_uses_only_verified_coordinate_pairs():
    far = candidate()
    missing = candidate()
    missing.dish.restaurant.location_verified = False
    missing.dish.restaurant.latitude = None
    missing.dish.restaurant.longitude = None
    preferences = FeedPreferences(user_lat=24.86, user_lng=67.0, max_distance_km=10)
    assert filter_candidates([far, missing], preferences) == [missing]


def test_vector_dimension_validation():
    with pytest.raises(ValidationError):
        FeedPreferences(taste_vector=[0.1, 0.2])
    with pytest.raises(ValueError, match="384"):
        calculate_cosine_similarity([1.0], [1.0])


def test_cosine_similarity():
    first = [1.0] + [0.0] * 383
    same = [2.0] + [0.0] * 383
    orthogonal = [0.0, 1.0] + [0.0] * 382
    assert calculate_cosine_similarity(first, same) == pytest.approx(1)
    assert calculate_cosine_similarity(first, orthogonal) == pytest.approx(0)


def test_weighted_scoring_uses_named_independent_signals():
    row = candidate()
    row = RankingCandidate(dish=row.dish, review_average=5.0, interaction_count=5)
    preferences = FeedPreferences(
        taste_vector=[1.0] + [0.0] * 383,
        budget_max=1000,
        user_lat=31.52,
        user_lng=74.35,
    )
    scored = score_candidate(row, preferences, maximum_interactions=10)
    expected = sum(WEIGHTS[name] * getattr(scored.signals, name) for name in WEIGHTS)
    assert scored.total_score == pytest.approx(expected)
    assert scored.signals.taste == pytest.approx(100)
    assert scored.signals.review == pytest.approx(100)
    assert scored.signals.popularity == pytest.approx(50)
    assert scored.distance_km == pytest.approx(0)
    assert scored.neutral_signals == {"context", "collaborative"}


def test_missing_vectors_and_unavailable_signals_are_neutral():
    scored = score_candidate(candidate(embedding=None), FeedPreferences(), maximum_interactions=0)
    assert scored.signals.taste == NEUTRAL_SCORE
    assert scored.signals.review == NEUTRAL_SCORE
    assert scored.signals.popularity == NEUTRAL_SCORE
    assert {"taste", "review", "popularity", "context", "collaborative"} <= set(
        scored.neutral_signals
    )


def test_preferences_reject_invalid_coordinate_and_budget_inputs():
    with pytest.raises(ValidationError):
        FeedPreferences(user_lat=31.5)
    with pytest.raises(ValidationError):
        FeedPreferences(budget_min=1000, budget_max=500)


def test_ranking_route_registered(client):
    assert any(route.path == "/ranking/feed/{user_id}" for route in client.app.routes)


def test_ranking_endpoint_missing_user_and_invalid_user(client):
    missing = client.get(f"/ranking/feed/{uuid.uuid4()}")
    invalid = client.get("/ranking/feed/not-a-uuid")
    assert missing.status_code == 404
    assert invalid.status_code == 422


def test_ranking_endpoint_rejects_wrong_vector_dimension(client, session):
    user = User(name="Vector User", email="vector@example.test")
    session.add(user)
    session.commit()
    response = client.get(
        f"/ranking/feed/{user.id}",
        params=[("taste_vector", "0.1"), ("taste_vector", "0.2")],
    )
    assert response.status_code == 422


def test_ranking_endpoint_success_response_types_stable_ties_and_empty(client, session):
    user = User(name="Rank User", email="rank@example.test")
    owner = restaurant(name="Rank Restaurant")
    session.add_all([user, owner])
    session.flush()
    second = dish(owner.id, name="Beta", embedding=None, price=Decimal("600"))
    first = dish(owner.id, name="Alpha", embedding=None, price=Decimal("600"))
    session.add_all([second, first])
    session.commit()

    response = client.get(f"/ranking/feed/{user.id}")
    assert response.status_code == 200
    payload = response.json()
    FeedResponse.model_validate(payload)
    assert payload["user_id"] == str(user.id)
    assert payload["total_candidates"] == 2
    assert [item["dish_name"] for item in payload["items"]] == ["Alpha", "Beta"]
    assert all(isinstance(item["match_percentage"], int) for item in payload["items"])
    assert "taste" in payload["neutral_signals"]

    empty = client.get(f"/ranking/feed/{user.id}?budget_max=1")
    assert empty.status_code == 200
    assert empty.json()["total_candidates"] == 0
    assert empty.json()["items"] == []


def test_ranking_endpoint_uses_integrated_reviews_and_interactions(client, session):
    user = User(name="Signal User", email="signals@example.test")
    owner = restaurant(name="Signal Restaurant")
    session.add_all([user, owner])
    session.flush()
    item = dish(owner.id, name="Observed Dish", embedding=None)
    session.add(item)
    session.flush()
    session.add_all(
        [
            Review(user_id=user.id, dish_id=item.id, rating=5, text="Excellent"),
            Interaction(user_id=user.id, dish_id=item.id, action="save"),
        ]
    )
    session.commit()

    response = client.get(f"/ranking/feed/{user.id}")
    assert response.status_code == 200
    signals = response.json()["items"][0]["signals"]
    assert signals["review"] == 100
    assert signals["popularity"] == 100
    assert "review" not in response.json()["neutral_signals"]
    assert "popularity" not in response.json()["neutral_signals"]
