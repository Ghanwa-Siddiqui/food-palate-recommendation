from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.ranking_client import (
    FeedResult,
    RankingBackendError,
    RankingUnavailableDataError,
    RankingUserNotFoundError,
    RankingValidationError,
)
from app.routers.ui import get_ranking_feed_client

USER_ID = UUID("11111111-1111-4111-8111-111111111111")


class StubRankingClient:
    def __init__(self, result=None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls = []

    def get_feed(self, user_id, params):
        self.calls.append((user_id, params))
        if self.error:
            raise self.error
        return self.result


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _override(stub):
    app.dependency_overrides[get_ranking_feed_client] = lambda: stub


def _feed_result(items):
    return FeedResult.model_validate(
        {
            "user_id": str(USER_ID),
            "total_candidates": len(items),
            "neutral_signals": ["taste"],
            "items": items,
        }
    )


def test_feed_prompts_without_calling_backend(client):
    stub = StubRankingClient()
    _override(stub)

    response = client.get("/app/feed")

    assert response.status_code == 200
    assert 'data-feed-state="prompt"' in response.text
    assert stub.calls == []


def test_feed_renders_ranked_results_and_safe_image_placeholder(client):
    stub = StubRankingClient(
        _feed_result(
            [
                {
                    "dish_id": "22222222-2222-4222-8222-222222222222",
                    "dish_name": "Chicken Karahi",
                    "restaurant_id": "33333333-3333-4333-8333-333333333333",
                    "restaurant_name": "Real Restaurant",
                    "price": 1250,
                    "match_percentage": 91,
                    "distance_km": None,
                }
            ]
        )
    )
    _override(stub)

    response = client.get(
        f"/app/feed?user_id={USER_ID}&budget_max=1500&require_halal=true"
        "&dietary_restrictions=vegetarian"
    )

    assert response.status_code == 200
    assert 'data-feed-state="success"' in response.text
    assert "Chicken Karahi" in response.text
    assert "PKR 1250" in response.text
    # Dish photo is matched by keyword from a local, always-available asset
    # (no per-dish image field exists on the Ranking API response) and falls
    # back safely via onerror, same pattern used on every other page.
    assert '/static/dishes/karahi.jpg' in response.text
    assert "onerror=\"this.style.display='none'\"" in response.text
    assert stub.calls == [
        (
            USER_ID,
            [
                ("budget_max", "1500"),
                ("require_halal", "true"),
                ("dietary_restrictions", "vegetarian"),
                ("limit", "20"),
            ],
        )
    ]


def test_feed_renders_empty_state(client):
    _override(StubRankingClient(_feed_result([])))

    response = client.get(f"/app/feed?user_id={USER_ID}")

    assert response.status_code == 200
    assert 'data-feed-state="empty"' in response.text
    assert "No dishes match" in response.text


@pytest.mark.parametrize(
    ("error", "state", "copy"),
    [
        (RankingValidationError(), "validation_error", "rejected these filters"),
        (RankingUserNotFoundError(), "missing_user", "user was not found"),
        (RankingUnavailableDataError(), "unavailable", "temporarily unavailable"),
        (RankingBackendError(), "backend_error", "could not be reached"),
    ],
)
def test_feed_renders_safe_api_error_states(client, error, state, copy):
    _override(StubRankingClient(error=error))

    response = client.get(f"/app/feed?user_id={USER_ID}")

    assert response.status_code == 200
    assert f'data-feed-state="{state}"' in response.text
    assert copy in response.text


def test_feed_handles_local_validation_without_backend_call(client):
    stub = StubRankingClient()
    _override(stub)

    response = client.get("/app/feed?user_id=not-a-uuid")

    assert response.status_code == 200
    assert 'data-feed-state="validation_error"' in response.text
    assert "valid user ID" in response.text
    assert stub.calls == []
